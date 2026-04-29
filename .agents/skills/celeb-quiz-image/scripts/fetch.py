"""Fetch free-licensed Wikimedia images for celeb-quiz JSONL entries.

Run from the repository root:
    python3 .agents/skills/celeb-quiz-image/scripts/fetch.py data/quizzes/name/list.jsonl

The script searches Korean Wikipedia first, then English Wikipedia, verifies the
selected page image is free-licensed via Commons metadata, downloads it into the
quiz's images/ directory, and atomically rewrites list.jsonl with enrichment
fields. It uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_USER_AGENT = "celeb-quiz-image/1.0 (+https://github.com/vkehfdl1/celeb-quiz) Python/3.x"
SEARCH_ENDPOINT = "https://{lang}.wikipedia.org/w/rest.php/v1/search/page"
PAGEIMAGE_ENDPOINT = "https://{lang}.wikipedia.org/w/api.php"
COMMONS_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FETCH_STATUSES = ("ok", "not_found", "no_free_image", "too_small", "error")


_last_call_at = 0.0


class FetchError(Exception):
    """Raised when a single entry cannot be fetched safely."""


def slugify_license(value: str) -> str:
    """Return a compact lowercase display slug for a license name."""
    text = strip_html(value).lower().strip()
    if not text:
        return "unknown"
    text = re.sub(r"[^a-z0-9.\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text or "unknown"


def strip_html(value: str) -> str:
    """Strip simple HTML tags and unescape entities from Wikimedia metadata."""
    text = re.sub(r"<[^>]*>", "", value or "")
    return html.unescape(text).strip()


def derive_id(entry: dict) -> str:
    """Use entry['id'] when ASCII-safe, else return a stable SHA1 fallback."""
    raw_id = str(entry.get("id", ""))
    try:
        raw_id.encode("ascii")
    except UnicodeEncodeError:
        raw_id = ""
    if raw_id:
        return raw_id
    name = str(entry.get("name", ""))
    fallback = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    print(f"[warn] missing/non-ASCII id for {name!r}; using {fallback}", file=sys.stderr)
    return fallback


def wikipedia_search(query: str, lang: str, user_agent: str = DEFAULT_USER_AGENT) -> list[dict]:
    """Search a Wikipedia language edition and return page hits."""
    params = urllib.parse.urlencode({"q": query, "limit": "5"})
    data = api_json(f"{SEARCH_ENDPOINT.format(lang=lang)}?{params}", user_agent)
    pages = data.get("pages", [])
    if not isinstance(pages, list):
        raise FetchError("malformed search response")
    return [page for page in pages if isinstance(page, dict)]


def wikipedia_pageimage(title: str, lang: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """Return pageimages API data for a page title with pilicense=free."""
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "pageimages",
            "titles": title,
            "piprop": "thumbnail|original|name",
            "pithumbsize": "800",
            "pilicense": "free",
            "format": "json",
        }
    )
    data = api_json(f"{PAGEIMAGE_ENDPOINT.format(lang=lang)}?{params}", user_agent)
    pages = data.get("query", {}).get("pages", {})
    if not isinstance(pages, dict) or not pages:
        raise FetchError("malformed pageimage response")
    first = next(iter(pages.values()))
    if not isinstance(first, dict):
        raise FetchError("malformed pageimage page")
    return first


def commons_license(filename: str, user_agent: str = DEFAULT_USER_AGENT) -> dict[str, str]:
    """Return license metadata for a Commons file name."""
    title = filename if filename.startswith("File:") else f"File:{filename}"
    params = urllib.parse.urlencode(
        {"action": "query", "prop": "imageinfo", "titles": title, "iiprop": "extmetadata", "format": "json"}
    )
    data = api_json(f"{COMMONS_ENDPOINT}?{params}", user_agent)
    pages = data.get("query", {}).get("pages", {})
    if not isinstance(pages, dict) or not pages:
        raise FetchError("malformed license response")
    page = next(iter(pages.values()))
    imageinfo = page.get("imageinfo", []) if isinstance(page, dict) else []
    extmetadata = imageinfo[0].get("extmetadata", {}) if imageinfo and isinstance(imageinfo[0], dict) else {}
    license_name = metadata_value(extmetadata, "LicenseShortName") or "Unknown"
    license_url = metadata_value(extmetadata, "LicenseUrl")
    artist_html = metadata_value(extmetadata, "Artist")
    credit_html = metadata_value(extmetadata, "Credit")
    attribution_parts = [part for part in (artist_html, license_name, credit_html or "via Wikimedia Commons") if part]
    return {
        "license": strip_html(license_name) or "Unknown",
        "license_short": slugify_license(license_name),
        "license_url": license_url,
        "artist": strip_html(artist_html),
        "attribution_html": ", ".join(attribution_parts),
    }


def download_image(source_url: str, destination: pathlib.Path, user_agent: str = DEFAULT_USER_AGENT) -> None:
    """Download an image URL to destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = api_bytes(source_url, user_agent)
    destination.write_bytes(payload)


def fetch_one(entry: dict, list_path: pathlib.Path, force: bool = False, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """Fetch and enrich one JSONL entry, returning the mutated entry."""
    if is_idempotent_hit(entry, list_path) and not force:
        print(f"[skip] {entry.get('name', '')} already ok", file=sys.stderr)
        return entry

    name = str(entry.get("name", "")).strip()
    if not name:
        raise FetchError("entry missing name")
    slug = derive_id(entry)
    query = f"{name} {entry.get('disambiguation', '')}".strip()

    found_lang = ""
    found_page = None
    for lang in ("ko", "en"):
        pages = wikipedia_search(query, lang, user_agent)
        found_page = pick_search_hit(name, pages)
        if found_page is None and lang == "en" and pages:
            found_page = pages[0]
        if found_page is not None:
            found_lang = lang
            break

    if found_page is None:
        entry["fetch_status"] = "not_found"
        return entry

    title = str(found_page.get("title", ""))
    pageimage = wikipedia_pageimage(title, found_lang, user_agent)
    original = pageimage.get("original")
    if not isinstance(original, dict) or not original.get("source"):
        entry["fetch_status"] = "no_free_image"
        return entry

    width = int(original.get("width") or 0)
    height = int(original.get("height") or 0)
    if max(width, height) < 400:
        entry["fetch_status"] = "too_small"
        return entry

    source_url = str(original.get("source"))
    filename = str(pageimage.get("imagename") or pathlib.PurePosixPath(urllib.parse.urlparse(source_url).path).name)
    license_info = commons_license(filename, user_agent)
    image_path = pathlib.Path("images") / f"{slug}{image_extension(source_url)}"
    download_image(source_url, list_path.parent / image_path, user_agent)

    entry.update(
        {
            "image_path": image_path.as_posix(),
            "image_source_url": source_url,
            "image_width": width,
            "image_height": height,
            "license": license_info["license"],
            "license_short": license_info["license_short"],
            "license_url": license_info["license_url"],
            "artist": license_info["artist"],
            "attribution_html": license_info["attribution_html"],
            "wikipedia_title": title,
            "wikipedia_url": f"https://{found_lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
            "wikipedia_lang": found_lang,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "fetch_status": "ok",
        }
    )
    return entry


def fetch_all(
    list_path: pathlib.Path | str,
    force: bool = False,
    limit: int | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, int]:
    """Fetch images for all entries in a JSONL file and atomically rewrite it."""
    path = pathlib.Path(list_path)
    entries = read_entries(path)
    processed = 0
    for index, entry in enumerate(entries):
        if limit is not None and processed >= limit:
            break
        processed += 1
        try:
            print(f"[fetch] {entry.get('name', f'#{index + 1}')}", file=sys.stderr)
            fetch_one(entry, path, force=force, user_agent=user_agent)
        except (FetchError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"[error] {entry.get('name', f'#{index + 1}')}: {exc}", file=sys.stderr)
            entry["fetch_status"] = "error"

    write_entries_atomic(path, entries)
    summary = summarize(entries, processed)
    print_summary(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Fetch free Wikimedia images for celeb-quiz list.jsonl entries.")
    parser.add_argument("list_jsonl", type=pathlib.Path, help="Path to list.jsonl")
    parser.add_argument("--force", action="store_true", help="Refetch even if fetch_status=ok and image exists")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N entries")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Override the Wikimedia User-Agent header")
    args = parser.parse_args(argv)
    fetch_all(args.list_jsonl, force=args.force, limit=args.limit, user_agent=args.user_agent)
    return 0


def metadata_value(extmetadata: dict, key: str) -> str:
    item = extmetadata.get(key, {}) if isinstance(extmetadata, dict) else {}
    value = item.get("value", "") if isinstance(item, dict) else ""
    return str(value)


def pick_search_hit(name: str, pages: list[dict]) -> dict | None:
    comparable_name = normalize_for_match(name)
    for page in pages:
        title = str(page.get("title", ""))
        comparable_title = normalize_for_match(title)
        if comparable_name and (comparable_name in comparable_title or comparable_title in comparable_name):
            return page
    return None


def normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def is_idempotent_hit(entry: dict, list_path: pathlib.Path) -> bool:
    if entry.get("fetch_status") != "ok" or not entry.get("image_path"):
        return False
    return (list_path.parent / str(entry["image_path"])).exists()


def image_extension(source_url: str) -> str:
    path = urllib.parse.urlparse(source_url).path
    suffix = pathlib.PurePosixPath(path).suffix.lower()
    return suffix if suffix in ALLOWED_EXTENSIONS else ".jpg"


def api_json(url: str, user_agent: str) -> dict:
    payload = api_bytes(url, user_agent)
    try:
        data = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise FetchError("invalid UTF-8 response") from exc
    if not isinstance(data, dict):
        raise FetchError("JSON response is not an object")
    return data


def api_bytes(url: str, user_agent: str) -> bytes:
    global _last_call_at
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    for attempt in range(5):
        rate_limit()
        try:
            with urllib.request.urlopen(request) as response:
                _last_call_at = time.monotonic()
                return response.read()
        except urllib.error.HTTPError as exc:
            _last_call_at = time.monotonic()
            if exc.code in (429, 503) and attempt < 4:
                time.sleep(2**attempt)
                continue
            raise
        except urllib.error.URLError:
            _last_call_at = time.monotonic()
            raise
    raise FetchError("retry attempts exhausted")


def rate_limit() -> None:
    global _last_call_at
    if _last_call_at <= 0:
        return
    elapsed = time.monotonic() - _last_call_at
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)


def read_entries(path: pathlib.Path) -> list[dict]:
    entries: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict):
            raise FetchError(f"line {line_number} is not a JSON object")
        entries.append(entry)
    return entries


def write_entries_atomic(path: pathlib.Path, entries: list[dict]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        finally:
            raise


def summarize(entries: list[dict], processed: int) -> dict[str, int]:
    summary = {"processed": processed}
    for status in FETCH_STATUSES:
        summary[status] = 0
    for entry in entries[:processed]:
        status = str(entry.get("fetch_status", "error"))
        if status not in summary:
            status = "error"
        summary[status] += 1
    return summary


def print_summary(summary: dict[str, int]) -> None:
    print(
        "[summary] "
        f"processed={summary.get('processed', 0)} "
        f"ok={summary.get('ok', 0)} "
        f"not_found={summary.get('not_found', 0)} "
        f"no_free_image={summary.get('no_free_image', 0)} "
        f"too_small={summary.get('too_small', 0)} "
        f"error={summary.get('error', 0)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
