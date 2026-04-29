"""Offline tests for the celeb-quiz Wikimedia image fetcher.

Run from the repository root with:
    python3 -m unittest scripts.tests.test_fetch -v

The fetcher lives under .agents/skills/celeb-quiz-image/scripts, so this test
module imports it by file path while keeping every urllib request mocked.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[2]
FETCH_PATH = ROOT / ".agents" / "skills" / "celeb-quiz-image" / "scripts" / "fetch.py"


def load_fetch_module():
    spec = importlib.util.spec_from_file_location("celeb_quiz_fetch", FETCH_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


fetch: Any = load_fetch_module()


class FakeResponse:
    def __init__(self, payload: bytes | dict):
        self.payload = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


def search_payload(title: str, page_id: int = 123) -> dict:
    return {"pages": [{"id": page_id, "key": title, "title": title, "description": "person"}]}


def empty_search_payload() -> dict:
    return {"pages": []}


def pageimage_payload(
    title: str = "이정후",
    filename: str = "Lee_Jung-hoo.jpg",
    source: str = "https://upload.wikimedia.org/wikipedia/commons/a/aa/Lee_Jung-hoo.jpg",
    width: int = 800,
    height: int = 1067,
) -> dict:
    return {
        "query": {
            "pages": {
                "123": {
                    "title": title,
                    "original": {"source": source, "width": width, "height": height},
                    "thumbnail": {"source": source, "width": width, "height": height},
                    "imagename": filename,
                }
            }
        }
    }


def no_original_payload(title: str = "이정후") -> dict:
    return {"query": {"pages": {"123": {"title": title, "imagename": "No_Free.jpg"}}}}


def license_payload(
    license_name: str = "CC BY-SA 4.0",
    license_url: str = "https://creativecommons.org/licenses/by-sa/4.0/",
    artist: str = '<a href="https://example.test">Photographer Name</a>',
) -> dict:
    return {
        "query": {
            "pages": {
                "456": {
                    "imageinfo": [
                        {
                            "extmetadata": {
                                "LicenseShortName": {"value": license_name},
                                "LicenseUrl": {"value": license_url},
                                "Artist": {"value": artist},
                                "Credit": {"value": "Wikimedia Commons"},
                            }
                        }
                    ]
                }
            }
        }
    }


def write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def route_urlopen(request, *args, **kwargs):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    if "/w/rest.php/v1/search/page" in url and "ko.wikipedia.org" in url:
        return FakeResponse(search_payload("이정후"))
    if "/w/rest.php/v1/search/page" in url and "en.wikipedia.org" in url:
        return FakeResponse(empty_search_payload())
    if "prop=pageimages" in url:
        return FakeResponse(pageimage_payload())
    if "prop=imageinfo" in url:
        return FakeResponse(license_payload())
    if "upload.wikimedia.org" in url:
        return FakeResponse(b"\xff\xd8\xff")
    raise AssertionError(f"unexpected URL: {url}")


class FetchTests(unittest.TestCase):
    def setUp(self) -> None:
        fetch._last_call_at = 0.0

    def test_slugify_license(self):
        self.assertEqual(fetch.slugify_license("CC BY-SA 4.0"), "cc-by-sa-4.0")
        self.assertEqual(fetch.slugify_license("Public domain"), "public-domain")
        self.assertEqual(fetch.slugify_license(""), "unknown")

    def test_strip_html(self):
        self.assertEqual(fetch.strip_html('<a href="x">Name</a>'), "Name")
        self.assertEqual(fetch.strip_html("Tom &amp; Jerry"), "Tom & Jerry")

    def test_fallback_id(self):
        entry = {"name": "무명", "category": "배우"}
        expected = hashlib.sha1("무명".encode("utf-8")).hexdigest()[:10]
        with patch("sys.stderr"):
            self.assertEqual(fetch.derive_id(entry), expected)

    def test_search_ko_hit(self):
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", side_effect=route_urlopen), patch("time.sleep"):
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}])

            summary = fetch.fetch_all(list_path)
            entry = read_jsonl(list_path)[0]

            self.assertEqual(summary["ok"], 1)
            self.assertEqual(entry["fetch_status"], "ok")
            self.assertEqual(entry["image_path"], "images/lee-jung-hoo.jpg")
            self.assertEqual(entry["image_width"], 800)
            self.assertEqual(entry["image_height"], 1067)
            self.assertEqual(entry["license"], "CC BY-SA 4.0")
            self.assertEqual(entry["license_short"], "cc-by-sa-4.0")
            self.assertEqual(entry["license_url"], "https://creativecommons.org/licenses/by-sa/4.0/")
            self.assertEqual(entry["artist"], "Photographer Name")
            self.assertIn("Photographer Name", entry["attribution_html"])
            self.assertEqual(entry["wikipedia_title"], "이정후")
            self.assertEqual(entry["wikipedia_url"], "https://ko.wikipedia.org/wiki/%EC%9D%B4%EC%A0%95%ED%9B%84")
            self.assertEqual(entry["wikipedia_lang"], "ko")
            self.assertIn("fetched_at", entry)
            self.assertTrue((Path(tmp) / "images" / "lee-jung-hoo.jpg").exists())

    def test_search_ko_miss_en_hit(self):
        def side_effect(request, *args, **kwargs):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if "ko.wikipedia.org" in url and "/w/rest.php/v1/search/page" in url:
                return FakeResponse(empty_search_payload())
            if "en.wikipedia.org" in url and "/w/rest.php/v1/search/page" in url:
                return FakeResponse(search_payload("Lee Jung-hoo"))
            if "prop=pageimages" in url:
                return FakeResponse(pageimage_payload(title="Lee Jung-hoo"))
            if "prop=imageinfo" in url:
                return FakeResponse(license_payload())
            if "upload.wikimedia.org" in url:
                return FakeResponse(b"\xff\xd8\xff")
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", side_effect=side_effect), patch("time.sleep"):
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}])
            fetch.fetch_all(list_path)
            self.assertEqual(read_jsonl(list_path)[0]["wikipedia_lang"], "en")

    def test_both_miss(self):
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", return_value=FakeResponse(empty_search_payload())), patch("time.sleep"):
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "missing", "name": "없는사람", "category": "배우"}])
            fetch.fetch_all(list_path)
            entry = read_jsonl(list_path)[0]
            self.assertEqual(entry["fetch_status"], "not_found")
            self.assertNotIn("image_path", entry)

    def test_no_free_image(self):
        def side_effect(request, *args, **kwargs):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if "/w/rest.php/v1/search/page" in url:
                return FakeResponse(search_payload("이정후"))
            if "prop=pageimages" in url:
                return FakeResponse(no_original_payload())
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", side_effect=side_effect), patch("time.sleep"):
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}])
            fetch.fetch_all(list_path)
            self.assertEqual(read_jsonl(list_path)[0]["fetch_status"], "no_free_image")

    def test_too_small(self):
        def side_effect(request, *args, **kwargs):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if "/w/rest.php/v1/search/page" in url:
                return FakeResponse(search_payload("이정후"))
            if "prop=pageimages" in url:
                return FakeResponse(pageimage_payload(width=200, height=200))
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", side_effect=side_effect), patch("time.sleep"):
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}])
            fetch.fetch_all(list_path)
            self.assertEqual(read_jsonl(list_path)[0]["fetch_status"], "too_small")

    def test_429_then_success(self):
        seen = {"ko_search": 0}

        def side_effect(request, *args, **kwargs):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if "/w/rest.php/v1/search/page" in url and "ko.wikipedia.org" in url:
                seen["ko_search"] += 1
                if seen["ko_search"] == 1:
                    raise HTTPError(url, 429, "Too Many Requests", Message(), None)
                return FakeResponse(search_payload("이정후"))
            if "prop=pageimages" in url:
                return FakeResponse(pageimage_payload())
            if "prop=imageinfo" in url:
                return FakeResponse(license_payload())
            if "upload.wikimedia.org" in url:
                return FakeResponse(b"\xff\xd8\xff")
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", side_effect=side_effect), patch("time.sleep"):
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}])
            fetch.fetch_all(list_path)
            self.assertEqual(seen["ko_search"], 2)
            self.assertEqual(read_jsonl(list_path)[0]["fetch_status"], "ok")

    def test_atomic_rewrite_preserves_on_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            list_path = Path(tmp) / "list.jsonl"
            original = '{"id":"ok","name":"A","category":"B"}\n'
            list_path.write_text(original, encoding="utf-8")
            bad_entries = [{"id": "changed", "name": "Changed", "category": "B", "fetch_status": "not_found"}]
            with patch.object(fetch, "read_entries", return_value=bad_entries), patch.object(fetch, "write_entries_atomic", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    fetch.fetch_all(list_path)
            self.assertEqual(list_path.read_text(encoding="utf-8"), original)
            self.assertFalse((Path(tmp) / "list.jsonl.tmp").exists())

    def test_idempotent_skip(self):
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen") as mocked:
            image_dir = Path(tmp) / "images"
            image_dir.mkdir()
            (image_dir / "lee-jung-hoo.jpg").write_bytes(b"image")
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수", "fetch_status": "ok", "image_path": "images/lee-jung-hoo.jpg"}])
            fetch.fetch_all(list_path)
            mocked.assert_not_called()

    def test_force_reruns(self):
        mocked = Mock(side_effect=route_urlopen)
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", mocked), patch("time.sleep"):
            image_dir = Path(tmp) / "images"
            image_dir.mkdir()
            (image_dir / "lee-jung-hoo.jpg").write_bytes(b"old")
            list_path = Path(tmp) / "list.jsonl"
            write_jsonl(list_path, [{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수", "fetch_status": "ok", "image_path": "images/lee-jung-hoo.jpg"}])
            fetch.fetch_all(list_path, force=True)
            self.assertGreater(mocked.call_count, 0)


if __name__ == "__main__":
    unittest.main()
