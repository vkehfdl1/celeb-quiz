"""celeb-quiz admin server: static file serving + REST API for quiz curation.

Run from the repository root:
    python3 scripts/admin_server.py [--port 8765] [--host 127.0.0.1]

Routes /admin/ -> /web/admin.html (302). Serves /web/* and /data/* statically.
Exposes mutation endpoints under /api/* for the admin UI to manage list.jsonl
and image files. After every mutation, validate.py is invoked in-process to
refresh quiz.json + index.json manifests.

Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import struct
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from email.parser import BytesParser
from email.policy import HTTP as HTTP_POLICY
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
DEFAULT_USER_AGENT = (
    "celeb-quiz-admin/1.0 (+https://github.com/vkehfdl1/celeb-quiz) Python/3.x"
)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_fetch_module = None
_validate_module = None
_module_lock = threading.Lock()


def _load_skill_module(rel_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / rel_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec at {rel_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_fetch_module():
    global _fetch_module
    with _module_lock:
        if _fetch_module is None:
            _fetch_module = _load_skill_module(
                ".agents/skills/celeb-quiz-image/scripts/fetch.py",
                "celeb_quiz_fetch",
            )
        return _fetch_module


def get_validate_module():
    global _validate_module
    with _module_lock:
        if _validate_module is None:
            _validate_module = _load_skill_module(
                ".agents/skills/celeb-quiz-setup/scripts/validate.py",
                "celeb_quiz_validate",
            )
        return _validate_module


class _HttpError(Exception):
    def __init__(self, status: int, message: str, payload: dict | None = None):
        self.status = status
        self.message = message
        self.payload = payload or {}
        super().__init__(f"{status} {message}")


def _slugify(name: str, used_ids: set[str]) -> str:
    """Derive a kebab-case ASCII slug from a name; fall back to hash if non-ASCII."""
    text = name.strip().lower()
    try:
        text.encode("ascii")
        ascii_safe = True
    except UnicodeEncodeError:
        ascii_safe = False
    if ascii_safe:
        slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60]
        if slug and ID_RE.match(slug):
            base = slug
        else:
            base = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    else:
        base = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _write_jsonl_atomic(path: pathlib.Path, entries: list[dict]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _sniff_image_dimensions(data: bytes) -> tuple[int, int]:
    """Return (width, height) for JPEG/PNG/WebP; (0, 0) if unparseable."""
    if len(data) < 24:
        return 0, 0
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
        except struct.error:
            return 0, 0
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                try:
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return int(w), int(h)
                except struct.error:
                    return 0, 0
            try:
                seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
            except struct.error:
                return 0, 0
            i += 2 + seg_len
        return 0, 0
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8 " and len(data) >= 30:
            try:
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return int(w), int(h)
            except struct.error:
                return 0, 0
        if chunk == b"VP8L" and len(data) >= 25:
            try:
                b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
                w = ((b1 & 0x3F) << 8 | b0) + 1
                h = ((b3 & 0x0F) << 10 | b2 << 2 | (b1 & 0xC0) >> 6) + 1
                return int(w), int(h)
            except (IndexError, struct.error):
                return 0, 0
        if chunk == b"VP8X" and len(data) >= 30:
            try:
                w = (data[24] | data[25] << 8 | data[26] << 16) + 1
                h = (data[27] | data[28] << 8 | data[29] << 16) + 1
                return int(w), int(h)
            except IndexError:
                return 0, 0
    return 0, 0


def _detect_image_extension(data: bytes, hint: str = "") -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    ext = pathlib.Path(hint).suffix.lower()
    if ext in ALLOWED_IMAGE_EXTS:
        return ext
    return ".jpg"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_path_param(value: str, regex: re.Pattern, label: str) -> str:
    if not regex.match(value):
        raise _HttpError(400, f"invalid {label}: {value!r}")
    return value


class AdminHandler(SimpleHTTPRequestHandler):
    """Static file server with REST API for quiz curation."""

    server_version = "celeb-quiz-admin/1.0"
    list_lock = threading.Lock()

    ROUTES: list[tuple[str, re.Pattern[str], str]] = [
        ("GET", re.compile(r"^/api/quizzes/?$"), "_get_quizzes"),
        ("GET", re.compile(r"^/api/quizzes/(?P<slug>[^/]+)/?$"), "_get_quiz"),
        ("POST", re.compile(r"^/api/quizzes/(?P<slug>[^/]+)/entries/?$"), "_post_entry"),
        ("DELETE", re.compile(r"^/api/quizzes/(?P<slug>[^/]+)/entries/(?P<eid>[^/]+)/?$"), "_delete_entry"),
        ("PUT", re.compile(r"^/api/quizzes/(?P<slug>[^/]+)/entries/(?P<eid>[^/]+)/image/?$"), "_put_image"),
        ("POST", re.compile(r"^/api/quizzes/(?P<slug>[^/]+)/entries/(?P<eid>[^/]+)/refetch/?$"), "_refetch_entry"),
    ]

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(REPO_ROOT), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[admin] {self.log_date_time_string()} {fmt % args}\n")

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path in ("/admin", "/admin/"):
            self._send_redirect("/web/admin.html")
            return
        if self._dispatch_api("GET"):
            return
        super().do_GET()

    def do_POST(self) -> None:
        if not self._dispatch_api("POST"):
            self._send_error(405, "method not allowed")

    def do_PUT(self) -> None:
        if not self._dispatch_api("PUT"):
            self._send_error(405, "method not allowed")

    def do_DELETE(self) -> None:
        if not self._dispatch_api("DELETE"):
            self._send_error(405, "method not allowed")

    def _dispatch_api(self, method: str) -> bool:
        path = urllib.parse.urlparse(self.path).path
        for rmethod, pattern, handler_name in self.ROUTES:
            if rmethod != method:
                continue
            m = pattern.match(path)
            if m:
                handler: Callable[..., None] = getattr(self, handler_name)
                try:
                    handler(**m.groupdict())
                except _HttpError as exc:
                    self._send_error(exc.status, exc.message, exc.payload)
                except Exception as exc:
                    self.log_message("UNHANDLED ERROR: %s", exc)
                    self._send_error(500, f"internal server error: {exc}")
                return True
        if path.startswith("/api/"):
            self._send_error(404, f"unknown api route: {path}")
            return True
        return False

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str, extra: dict | None = None) -> None:
        payload: dict[str, Any] = {"error": message}
        if extra:
            payload.update(extra)
        self._send_json(status, payload)

    def _send_redirect(self, location: str, status: int = 302) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise _HttpError(400, f"invalid JSON body: {exc}")
        if not isinstance(data, dict):
            raise _HttpError(400, "JSON body must be an object")
        return data

    def _read_raw_body(self, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return b""
        if length > max_bytes:
            raise _HttpError(413, f"upload too large: {length} > {max_bytes}")
        return self.rfile.read(length)

    def _quiz_dir(self, slug: str) -> pathlib.Path:
        slug = _validate_path_param(slug, SLUG_RE, "slug")
        return DATA_DIR / "quizzes" / slug

    def _list_path(self, slug: str) -> pathlib.Path:
        return self._quiz_dir(slug) / "list.jsonl"

    def _refresh_manifests(self, quiz_dir: pathlib.Path) -> None:
        validate = get_validate_module()
        try:
            validate.main(["--quiz-dir", str(quiz_dir)])
        except SystemExit as exc:
            if exc.code not in (0, None):
                self.log_message("validate exited code %s", exc.code)
        except Exception as exc:
            self.log_message("validate.main raised: %s", exc)

    # ---------- API endpoints ----------

    def _get_quizzes(self) -> None:
        index_path = DATA_DIR / "quizzes" / "index.json"
        if not index_path.exists():
            raise _HttpError(404, "no quizzes index found")
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise _HttpError(500, f"corrupt index.json: {exc}")
        self._send_json(200, data)

    def _get_quiz(self, slug: str) -> None:
        quiz_dir = self._quiz_dir(slug)
        if not quiz_dir.exists():
            raise _HttpError(404, f"quiz not found: {slug}")
        manifest_path = quiz_dir / "quiz.json"
        list_path = quiz_dir / "list.jsonl"
        if not list_path.exists():
            raise _HttpError(404, f"quiz list missing: {slug}")
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        with self.list_lock:
            entries = _read_jsonl(list_path)
        self._send_json(200, {"manifest": manifest, "entries": entries})

    def _post_entry(self, slug: str) -> None:
        body = self._read_json_body()
        name = (body.get("name") or "").strip()
        category = (body.get("category") or "").strip()
        if not name:
            raise _HttpError(400, "missing required field: name")
        if not category:
            raise _HttpError(400, "missing required field: category")
        quiz_dir = self._quiz_dir(slug)
        if not quiz_dir.exists():
            raise _HttpError(404, f"quiz not found: {slug}")
        list_path = self._list_path(slug)

        with self.list_lock:
            entries = _read_jsonl(list_path)
            used_ids = {e.get("id", "") for e in entries}
            entry_id = (body.get("id") or "").strip()
            if entry_id:
                if not ID_RE.match(entry_id):
                    raise _HttpError(400, f"invalid id format: {entry_id!r}")
                if entry_id in used_ids:
                    raise _HttpError(409, f"id collision: {entry_id}")
            else:
                entry_id = _slugify(name, used_ids)
            new_entry: dict[str, Any] = {
                "id": entry_id,
                "name": name,
                "category": category,
            }
            disambiguation = (body.get("disambiguation") or "").strip()
            if disambiguation:
                new_entry["disambiguation"] = disambiguation
            entries.append(new_entry)
            _write_jsonl_atomic(list_path, entries)

        if body.get("auto_fetch"):
            try:
                fetch = get_fetch_module()
                fetch.fetch_one(
                    new_entry,
                    list_path,
                    force=False,
                    user_agent=DEFAULT_USER_AGENT,
                    source="auto",
                )
                with self.list_lock:
                    entries = _read_jsonl(list_path)
                    for i, e in enumerate(entries):
                        if e.get("id") == entry_id:
                            entries[i] = new_entry
                            break
                    _write_jsonl_atomic(list_path, entries)
            except Exception as exc:
                new_entry["fetch_status"] = "error"
                self.log_message("auto_fetch failed for %s: %s", entry_id, exc)

        self._refresh_manifests(quiz_dir)
        self._send_json(201, {"entry": new_entry})

    def _delete_entry(self, slug: str, eid: str) -> None:
        eid = _validate_path_param(eid, ID_RE, "entry id")
        quiz_dir = self._quiz_dir(slug)
        list_path = self._list_path(slug)
        if not list_path.exists():
            raise _HttpError(404, f"quiz not found: {slug}")
        removed_image: str | None = None
        with self.list_lock:
            entries = _read_jsonl(list_path)
            new_entries = []
            target = None
            for e in entries:
                if e.get("id") == eid:
                    target = e
                else:
                    new_entries.append(e)
            if target is None:
                raise _HttpError(404, f"entry not found: {eid}")
            image_path = target.get("image_path")
            if image_path and isinstance(image_path, str):
                try:
                    img_full = (quiz_dir / image_path).resolve()
                    images_dir = (quiz_dir / "images").resolve()
                    if img_full.is_relative_to(images_dir) and img_full.exists():
                        img_full.unlink()
                        removed_image = image_path
                except (ValueError, OSError) as exc:
                    self.log_message("could not remove image %s: %s", image_path, exc)
            _write_jsonl_atomic(list_path, new_entries)
        self._refresh_manifests(quiz_dir)
        self._send_json(200, {"id": eid, "removed_image": removed_image})

    def _put_image(self, slug: str, eid: str) -> None:
        eid = _validate_path_param(eid, ID_RE, "entry id")
        quiz_dir = self._quiz_dir(slug)
        list_path = self._list_path(slug)
        if not list_path.exists():
            raise _HttpError(404, f"quiz not found: {slug}")
        content_type = self.headers.get("Content-Type", "")
        image_bytes: bytes
        source_url: str = ""
        upload_filename: str = ""
        if content_type.startswith("application/json"):
            body = self._read_json_body()
            url = (body.get("url") or "").strip()
            if not url:
                raise _HttpError(400, "missing url field")
            if not (url.startswith("http://") or url.startswith("https://")):
                raise _HttpError(400, "url must be http(s)")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    image_bytes = resp.read(MAX_UPLOAD_BYTES + 1)
            except urllib.error.URLError as exc:
                raise _HttpError(400, f"download failed: {exc}")
            if len(image_bytes) > MAX_UPLOAD_BYTES:
                raise _HttpError(413, "downloaded image too large")
            source_url = url
            upload_filename = url.rsplit("/", 1)[-1]
        elif content_type.startswith("multipart/"):
            raw = self._read_raw_body()
            header_block = b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n"
            parser = BytesParser(policy=HTTP_POLICY)
            msg = parser.parsebytes(header_block + raw)
            if not msg.is_multipart():
                raise _HttpError(400, "malformed multipart body")
            image_bytes = b""
            for part in msg.iter_parts():
                cd = part.get("Content-Disposition", "")
                if "name=\"image\"" in cd or "name='image'" in cd or 'name="image"' in cd:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        image_bytes = payload
                    upload_filename = part.get_filename() or "upload"
                    break
            if not image_bytes:
                raise _HttpError(400, "missing image field in multipart")
        else:
            raise _HttpError(400, "unsupported Content-Type for image upload")

        if not image_bytes:
            raise _HttpError(400, "empty image data")
        ext = _detect_image_extension(image_bytes, upload_filename)
        if ext not in ALLOWED_IMAGE_EXTS:
            raise _HttpError(400, f"unsupported image type: {ext}")
        width, height = _sniff_image_dimensions(image_bytes)

        with self.list_lock:
            entries = _read_jsonl(list_path)
            target_idx = None
            for i, e in enumerate(entries):
                if e.get("id") == eid:
                    target_idx = i
                    break
            if target_idx is None:
                raise _HttpError(404, f"entry not found: {eid}")
            (quiz_dir / "images").mkdir(parents=True, exist_ok=True)
            relative_image_path = f"images/{eid}{ext}"
            image_full = quiz_dir / relative_image_path
            tmp_image = image_full.with_name(image_full.name + ".tmp")
            try:
                tmp_image.write_bytes(image_bytes)
                os.replace(tmp_image, image_full)
            except OSError as exc:
                if tmp_image.exists():
                    try:
                        tmp_image.unlink()
                    except OSError:
                        pass
                raise _HttpError(500, f"failed to write image: {exc}")
            entry = entries[target_idx]
            old_image_path = entry.get("image_path")
            if old_image_path and old_image_path != relative_image_path:
                try:
                    old_full = (quiz_dir / old_image_path).resolve()
                    images_dir = (quiz_dir / "images").resolve()
                    if old_full.is_relative_to(images_dir) and old_full.exists():
                        old_full.unlink()
                except (ValueError, OSError):
                    pass
            entry.update({
                "image_path": relative_image_path,
                "image_source_url": source_url,
                "image_width": width,
                "image_height": height,
                "license": "User upload" if not source_url else "Unknown",
                "license_short": "user-upload" if not source_url else "unknown",
                "license_url": "",
                "artist": "",
                "attribution_html": "User upload" if not source_url else f"Source: {source_url}",
                "image_source": "user-upload" if not source_url else "user-url",
                "fetched_at": _now_iso(),
                "fetch_status": "ok",
            })
            entries[target_idx] = entry
            _write_jsonl_atomic(list_path, entries)
        self._refresh_manifests(quiz_dir)
        self._send_json(200, {
            "image_path": relative_image_path,
            "image_width": width,
            "image_height": height,
        })

    def _refetch_entry(self, slug: str, eid: str) -> None:
        eid = _validate_path_param(eid, ID_RE, "entry id")
        quiz_dir = self._quiz_dir(slug)
        list_path = self._list_path(slug)
        if not list_path.exists():
            raise _HttpError(404, f"quiz not found: {slug}")
        with self.list_lock:
            entries = _read_jsonl(list_path)
            target_idx = None
            for i, e in enumerate(entries):
                if e.get("id") == eid:
                    target_idx = i
                    break
            if target_idx is None:
                raise _HttpError(404, f"entry not found: {eid}")
            entry = entries[target_idx]
        fetch = get_fetch_module()
        try:
            fetch.fetch_one(entry, list_path, force=True, user_agent=DEFAULT_USER_AGENT, source="auto")
        except Exception as exc:
            entry["fetch_status"] = "error"
            self.log_message("refetch failed for %s: %s", eid, exc)
        with self.list_lock:
            entries = _read_jsonl(list_path)
            for i, e in enumerate(entries):
                if e.get("id") == eid:
                    entries[i] = entry
                    break
            _write_jsonl_atomic(list_path, entries)
        self._refresh_manifests(quiz_dir)
        self._send_json(200, {"entry": entry})


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), AdminHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="celeb-quiz admin server (static + REST API)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    server = make_server(host=args.host, port=args.port)
    sys.stderr.write("celeb-quiz admin server\n")
    sys.stderr.write(f"  Repo root : {REPO_ROOT}\n")
    sys.stderr.write(f"  Bind      : {args.host}:{args.port}\n")
    sys.stderr.write(f"  Quiz app  : http://localhost:{args.port}/web/\n")
    sys.stderr.write(f"  Admin UI  : http://localhost:{args.port}/admin/\n\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nshutting down\n")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
