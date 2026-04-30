"""Fetch images for celeb-quiz JSONL entries.

Run from the repository root:
    python3 .agents/skills/celeb-quiz-image/scripts/fetch.py data/quizzes/name/list.jsonl

By default the script searches Korean Wikipedia first, then English Wikipedia,
and keeps the historic free-licensed Wikimedia behavior. Optional source modes
can relax the license filter and fall back to DuckDuckGo/Bing image search for
private/non-commercial quizzes. It uses only Python's standard library.
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
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FETCH_STATUSES = ("ok", "not_found", "no_free_image", "too_small", "error")
SOURCES = ("wiki-free", "wiki-any", "auto")


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


def wikipedia_pageimage(title: str, lang: str, user_agent: str = DEFAULT_USER_AGENT, license_filter: str | None = "free") -> dict:
    """Return pageimages API data for a page title, optionally filtered by license."""
    params_dict = {
        "action": "query",
        "prop": "pageimages",
        "titles": title,
        "piprop": "thumbnail|original|name",
        "pithumbsize": "800",
        "format": "json",
    }
    if license_filter:
        params_dict["pilicense"] = license_filter
    params = urllib.parse.urlencode(params_dict)
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


def duckduckgo_image_search(query: str, user_agent: str = DEFAULT_USER_AGENT) -> dict | None:
    """Return the first usable DuckDuckGo image result for a query."""
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Referer": "https://duckduckgo.com/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    search_url = "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": query, "iax": "images", "ia": "images"})
    html_text = api_bytes(search_url, user_agent, headers=headers).decode("utf-8", errors="replace")
    token_match = re.search(r"vqd=([\d-]+)", html_text) or re.search(r'vqd="([^"]+)"', html_text)
    if not token_match:
        return None
    params = urllib.parse.urlencode({"l": "us-en", "o": "json", "q": query, "vqd": token_match.group(1), "f": ",,,", "p": "1", "v7exp": "a"})
    data = api_json(f"https://duckduckgo.com/i.js?{params}", user_agent, headers=headers)
    results = data.get("results", [])
    if not isinstance(results, list):
        return None
    for result in results:
        if not isinstance(result, dict):
            continue
        image_url = str(result.get("image", ""))
        if image_extension(image_url) not in ALLOWED_EXTENSIONS:
            continue
        width = int(result.get("width") or 0)
        height = int(result.get("height") or 0)
        if width and height and max(width, height) < 200:
            continue
        return {"image_url": image_url, "image_width": width, "image_height": height, "source": "duckduckgo"}
    return None


def bing_image_search(query: str, user_agent: str = DEFAULT_USER_AGENT) -> dict | None:
    """Return the first usable Bing Images result for a query."""
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    params = urllib.parse.urlencode({"q": query, "first": "1", "count": "10", "adlt": "moderate"})
    html_text = api_bytes(f"https://www.bing.com/images/async?{params}", user_agent, headers=headers).decode("utf-8", errors="replace")
    matches = re.findall(r"murl&quot;:&quot;(https?://[^&]+)&quot;", html_text)
    if not matches:
        matches = re.findall(r'"murl":"(https?://[^"]+)"', html_text)
    for match in matches:
        image_url = html.unescape(match)
        if image_extension(image_url) in ALLOWED_EXTENSIONS:
            return {"image_url": image_url, "image_width": 0, "image_height": 0, "source": "bing"}
    return None


def fetch_one(
    entry: dict,
    list_path: pathlib.Path,
    force: bool = False,
    user_agent: str = DEFAULT_USER_AGENT,
    source: str = "wiki-free",
) -> dict:
    """Fetch and enrich one JSONL entry, returning the mutated entry.

    Wikipedia sources keep the historic 400px long-side validation. Web image
    fallbacks may not expose dimensions before download, so zero dimensions do
    not trigger the too_small guard for DuckDuckGo/Bing results.
    """
    if is_idempotent_hit(entry, list_path) and not force:
        print(f"[skip] {entry.get('name', '')} already ok", file=sys.stderr)
        return entry
    if source not in SOURCES:
        raise FetchError(f"unknown source: {source}")

    name = str(entry.get("name", "")).strip()
    if not name:
        raise FetchError("entry missing name")
    query = f"{name} {entry.get('disambiguation', '')}".strip()

    cascade = source == "auto"
    if source in ("wiki-free", "auto"):
        try:
            result = fetch_wikipedia_source(entry, list_path, name, query, user_agent, license_filter="free", source_label="wikipedia-free", cascade_too_small=cascade)
        except (FetchError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError, ValueError) as exc:
            if source == "wiki-free":
                raise
            print(f"[warn] {name}: wiki-free failed ({exc}); trying next source", file=sys.stderr)
            result = None
        if result is not None:
            return result
        if source == "wiki-free":
            entry["fetch_status"] = "not_found" if entry.get("_wiki_search_miss") else "no_free_image"
            entry.pop("_wiki_search_miss", None)
            return entry

    if source in ("wiki-any", "auto"):
        try:
            result = fetch_wikipedia_source(entry, list_path, name, query, user_agent, license_filter=None, source_label="wikipedia-any", cascade_too_small=cascade)
        except (FetchError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError, ValueError) as exc:
            if source == "wiki-any":
                raise
            print(f"[warn] {name}: wiki-any failed ({exc}); trying next source", file=sys.stderr)
            result = None
        if result is not None:
            return result
        if source == "wiki-any":
            entry["fetch_status"] = "not_found"
            entry.pop("_wiki_search_miss", None)
            return entry

    entry.pop("_wiki_search_miss", None)
    for fn, source_label in ((duckduckgo_image_search, "duckduckgo"), (bing_image_search, "bing")):
        try:
            result = fn(query, user_agent)
        except (FetchError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"[warn] {name}: {source_label} failed ({exc}); trying next source", file=sys.stderr)
            continue
        if result:
            try:
                entry.pop("_wiki_small_fallback", None)
                return enrich_from_web(entry, result, list_path, user_agent, source_label)
            except (FetchError, urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
                print(f"[warn] {name}: {source_label} download failed ({exc}); trying next source", file=sys.stderr)
                continue

    stash = entry.pop("_wiki_small_fallback", None)
    if stash is not None:
        print(f"[fallback] {name}: using small wiki image ({stash['width']}x{stash['height']})", file=sys.stderr)
        return enrich_from_wikipedia(
            entry, stash["pageimage"], stash["title"], stash["found_lang"],
            list_path, user_agent, stash["source_label"], stash["width"], stash["height"],
        )

    entry["fetch_status"] = "not_found"
    return entry


def fetch_wikipedia_source(
    entry: dict,
    list_path: pathlib.Path,
    name: str,
    query: str,
    user_agent: str,
    license_filter: str | None,
    source_label: str,
    cascade_too_small: bool = False,
) -> dict | None:
    """Try one Wikipedia source mode and return enriched entry on success."""
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
        entry["_wiki_search_miss"] = True
        return None

    title = str(found_page.get("title", ""))
    pageimage = wikipedia_pageimage(title, found_lang, user_agent, license_filter=license_filter)
    original = pageimage.get("original")
    if not isinstance(original, dict) or not original.get("source"):
        entry.pop("_wiki_search_miss", None)
        return None

    width = int(original.get("width") or 0)
    height = int(original.get("height") or 0)
    if max(width, height) < 400:
        if not cascade_too_small:
            entry["fetch_status"] = "too_small"
            return entry
        entry.pop("_wiki_search_miss", None)
        if "_wiki_small_fallback" not in entry:
            entry["_wiki_small_fallback"] = {
                "pageimage": pageimage, "title": title, "found_lang": found_lang,
                "source_label": source_label, "width": width, "height": height,
            }
        return None

    return enrich_from_wikipedia(entry, pageimage, title, found_lang, list_path, user_agent, source_label, width, height)


def enrich_from_wikipedia(
    entry: dict,
    pageimage: dict,
    title: str,
    found_lang: str,
    list_path: pathlib.Path,
    user_agent: str,
    source_label: str,
    width: int,
    height: int,
) -> dict:
    """Download and attach metadata for a Wikipedia page image."""
    slug = derive_id(entry)
    original = pageimage.get("original", {})
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
            "image_source": source_label,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "fetch_status": "ok",
        }
    )
    entry.pop("_wiki_search_miss", None)
    return entry


def enrich_from_web(entry: dict, result: dict, list_path: pathlib.Path, user_agent: str, source_label: str) -> dict:
    """Download and attach metadata for a web image search result."""
    slug = derive_id(entry)
    source_url = str(result.get("image_url", ""))
    image_path = pathlib.Path("images") / f"{slug}{image_extension(source_url)}"
    download_image(source_url, list_path.parent / image_path, user_agent)
    entry.update(
        {
            "image_path": image_path.as_posix(),
            "image_source_url": source_url,
            "image_width": int(result.get("image_width") or 0),
            "image_height": int(result.get("image_height") or 0),
            "license": "unknown",
            "license_short": "unknown",
            "license_url": "",
            "artist": "",
            "attribution_html": f"Source: {source_label}",
            "image_source": source_label,
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
    source: str = "wiki-free",
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
            fetch_one(entry, path, force=force, user_agent=user_agent, source=source)
        except (FetchError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"[error] {entry.get('name', f'#{index + 1}')}: {exc}", file=sys.stderr)
            entry["fetch_status"] = "error"

    write_entries_atomic(path, entries)
    summary = summarize(entries, processed)
    print_summary(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Fetch images for celeb-quiz list.jsonl entries.")
    parser.add_argument("list_jsonl", type=pathlib.Path, help="Path to list.jsonl")
    parser.add_argument("--force", action="store_true", help="Refetch even if fetch_status=ok and image exists")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N entries")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Override the Wikimedia User-Agent header")
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="wiki-free",
        help="Image source strategy: wiki-free (default), wiki-any, or auto fallback chain",
    )
    parser.add_argument("--allow-non-free", action="store_true", help="Alias for --source=auto for private/non-commercial use")
    args = parser.parse_args(argv)
    source = "auto" if args.allow_non_free else args.source
    fetch_all(args.list_jsonl, force=args.force, limit=args.limit, user_agent=args.user_agent, source=source)
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


def api_json(url: str, user_agent: str, headers: dict[str, str] | None = None) -> dict:
    payload = api_bytes(url, user_agent, headers=headers)
    try:
        data = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise FetchError("invalid UTF-8 response") from exc
    if not isinstance(data, dict):
        raise FetchError("JSON response is not an object")
    return data


def api_bytes(url: str, user_agent: str, headers: dict[str, str] | None = None) -> bytes:
    global _last_call_at
    request_headers = {"User-Agent": user_agent}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
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
