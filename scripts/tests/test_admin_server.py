"""Tests for celeb-quiz admin server (scripts/admin_server.py).

Run: python3 -m unittest scripts.tests.test_admin_server -v
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "admin_server.py"

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xc6\xa7\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _load_admin_server():
    spec = importlib.util.spec_from_file_location("admin_server", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_temp_quiz_dir(root: pathlib.Path, slug: str = "test-quiz", n_entries: int = 3) -> pathlib.Path:
    quiz_dir = root / "data" / "quizzes" / slug
    images_dir = quiz_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    list_path = quiz_dir / "list.jsonl"
    entries = []
    for i in range(n_entries):
        eid = f"person-{i+1}"
        (images_dir / f"{eid}.png").write_bytes(PNG_1X1)
        entries.append({
            "id": eid,
            "name": f"테스트{i+1}",
            "category": "테스트",
            "image_path": f"images/{eid}.png",
            "image_source_url": f"https://example.com/{eid}.png",
            "image_width": 1,
            "image_height": 1,
            "license": "CC0",
            "license_short": "cc0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "artist": "Test",
            "attribution_html": "Test, CC0",
            "fetched_at": "2026-04-30T00:00:00Z",
            "fetch_status": "ok",
        })
    with list_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    quiz_json = {
        "schema_version": 1,
        "name": slug,
        "title": f"Test {slug}",
        "category": "테스트",
        "count": n_entries,
        "valid_count": n_entries,
        "default_countdown_seconds": 7,
        "list_path": "list.jsonl",
        "created_at": "2026-04-30T00:00:00Z",
        "updated_at": "2026-04-30T00:00:00Z",
        "generator": {"setup_skill_version": "1.0.0"},
    }
    (quiz_dir / "quiz.json").write_text(
        json.dumps(quiz_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    index_json = {
        "schema_version": 1,
        "quizzes": [
            {"name": slug, "title": f"Test {slug}", "count": n_entries, "valid_count": n_entries, "category": "테스트"},
        ],
        "updated_at": "2026-04-30T00:00:00Z",
    }
    (root / "data" / "quizzes" / "index.json").write_text(
        json.dumps(index_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    web = root / "web"
    web.mkdir(parents=True, exist_ok=True)
    (web / "index.html").write_text("<html><body>quiz app</body></html>", encoding="utf-8")
    (web / "admin.html").write_text("<html><body>admin ui</body></html>", encoding="utf-8")
    return quiz_dir


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


@contextlib.contextmanager
def start_test_server(repo_root: pathlib.Path, admin_module):
    saved_root = admin_module.REPO_ROOT
    saved_data = admin_module.DATA_DIR
    admin_module.REPO_ROOT = repo_root
    admin_module.DATA_DIR = repo_root / "data"
    repo_str = str(repo_root)

    class _PatchedHandler(admin_module.AdminHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=repo_str, **kwargs)

        def log_message(self, fmt, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _PatchedHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, port
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
        admin_module.REPO_ROOT = saved_root
        admin_module.DATA_DIR = saved_data


def http_request(port: int, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class RecordingValidate:
    def __init__(self):
        self.calls: list[list[str]] = []

    def main(self, argv):
        self.calls.append(list(argv))
        return 0


class AdminServerTests(unittest.TestCase):

    def setUp(self):
        self.admin = _load_admin_server()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = pathlib.Path(self._tmp.name)
        make_temp_quiz_dir(self.tmp_root, slug="test-quiz", n_entries=3)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch_validate(self, recorder):
        return patch.object(self.admin, "get_validate_module", return_value=recorder)

    def test_admin_path_redirects_to_web_admin_html(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/admin/", method="GET")
            opener = urllib.request.build_opener(_NoRedirectHandler())
            try:
                opener.open(req, timeout=5)
                self.fail("expected redirect")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 302)
                self.assertEqual(e.headers["Location"], "/web/admin.html")

    def test_static_files_still_served(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, body = http_request(port, "GET", "/web/index.html")
            self.assertEqual(status, 200)
            self.assertIn(b"quiz app", body)

    def test_unknown_api_route_returns_404(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, headers, body = http_request(port, "GET", "/api/nonexistent")
            self.assertEqual(status, 404)
            self.assertIn("application/json", headers.get("Content-Type", ""))
            self.assertIn("error", json.loads(body))

    def test_method_not_allowed_for_non_api(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _b = http_request(port, "POST", "/", body=b"", headers={"Content-Length": "0"})
            self.assertEqual(status, 405)

    def test_localhost_binding(self):
        server = self.admin.make_server(host="127.0.0.1", port=0)
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.server_close()

    def test_list_quizzes_returns_index_json(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, body = http_request(port, "GET", "/api/quizzes")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(len(data["quizzes"]), 1)
            self.assertEqual(data["quizzes"][0]["name"], "test-quiz")

    def test_list_quizzes_404_when_no_index(self):
        (self.tmp_root / "data" / "quizzes" / "index.json").unlink()
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _b = http_request(port, "GET", "/api/quizzes")
            self.assertEqual(status, 404)

    def test_get_quiz_joins_manifest_and_entries(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, body = http_request(port, "GET", "/api/quizzes/test-quiz")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["manifest"]["name"], "test-quiz")
            self.assertEqual(len(data["entries"]), 3)

    def test_get_quiz_404_for_missing_slug(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _b = http_request(port, "GET", "/api/quizzes/nope")
            self.assertEqual(status, 404)

    def test_get_quiz_blocks_path_traversal(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _b = http_request(port, "GET", "/api/quizzes/..%2Fetc")
            self.assertIn(status, (400, 404))

    def test_post_entry_appends_to_jsonl(self):
        rec = RecordingValidate()
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"name": "신규", "category": "테스트", "id": "new-one"}).encode("utf-8")
            status, _h, resp = http_request(
                port, "POST", "/api/quizzes/test-quiz/entries",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(json.loads(resp)["entry"]["id"], "new-one")
        list_path = self.tmp_root / "data" / "quizzes" / "test-quiz" / "list.jsonl"
        ids = [json.loads(l)["id"] for l in list_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertIn("new-one", ids)
        self.assertGreaterEqual(len(rec.calls), 1)

    def test_post_entry_with_auto_fetch_calls_fetcher(self):
        rec = RecordingValidate()

        class FakeFetch:
            calls: list[dict] = []

            @classmethod
            def fetch_one(cls, entry, list_path, force, user_agent, source):
                cls.calls.append({"entry_id": entry.get("id"), "force": force, "source": source})
                entry["fetch_status"] = "ok"
                entry["image_path"] = f"images/{entry['id']}.jpg"
                return entry

        with self._patch_validate(rec), \
             patch.object(self.admin, "get_fetch_module", return_value=FakeFetch), \
             start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"name": "오토", "category": "테스트", "id": "auto-one", "auto_fetch": True}).encode("utf-8")
            status, _h, _resp = http_request(
                port, "POST", "/api/quizzes/test-quiz/entries",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(len(FakeFetch.calls), 1)
            self.assertEqual(FakeFetch.calls[0]["source"], "auto")
            self.assertFalse(FakeFetch.calls[0]["force"])

    def test_post_entry_400_on_missing_name(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"category": "테스트"}).encode("utf-8")
            status, _h, _b = http_request(
                port, "POST", "/api/quizzes/test-quiz/entries",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 400)

    def test_post_entry_400_on_invalid_id(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"name": "x", "category": "y", "id": "Bad ID"}).encode("utf-8")
            status, _h, _b = http_request(
                port, "POST", "/api/quizzes/test-quiz/entries",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 400)

    def test_post_entry_409_on_duplicate_id(self):
        rec = RecordingValidate()
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"name": "중복", "category": "테스트", "id": "person-1"}).encode("utf-8")
            status, _h, _b = http_request(
                port, "POST", "/api/quizzes/test-quiz/entries",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 409)

    def test_post_entry_id_auto_derived_from_name(self):
        rec = RecordingValidate()
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"name": "Lee Jung Hoo", "category": "야구"}).encode("utf-8")
            status, _h, resp = http_request(
                port, "POST", "/api/quizzes/test-quiz/entries",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(json.loads(resp)["entry"]["id"], "lee-jung-hoo")

    def test_delete_entry_removes_from_jsonl_and_image(self):
        rec = RecordingValidate()
        list_path = self.tmp_root / "data" / "quizzes" / "test-quiz" / "list.jsonl"
        img_path = self.tmp_root / "data" / "quizzes" / "test-quiz" / "images" / "person-1.png"
        self.assertTrue(img_path.exists())
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, resp = http_request(port, "DELETE", "/api/quizzes/test-quiz/entries/person-1")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(resp)["id"], "person-1")
        ids = [json.loads(l)["id"] for l in list_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertNotIn("person-1", ids)
        self.assertFalse(img_path.exists())

    def test_delete_entry_404_when_not_found(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _b = http_request(port, "DELETE", "/api/quizzes/test-quiz/entries/nonexistent")
            self.assertEqual(status, 404)

    def test_delete_entry_no_image_field_still_succeeds(self):
        rec = RecordingValidate()
        list_path = self.tmp_root / "data" / "quizzes" / "test-quiz" / "list.jsonl"
        entries = [json.loads(l) for l in list_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        for e in entries:
            if e["id"] == "person-2":
                e.pop("image_path", None)
        with list_path.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, resp = http_request(port, "DELETE", "/api/quizzes/test-quiz/entries/person-2")
            self.assertEqual(status, 200)
            self.assertIsNone(json.loads(resp)["removed_image"])

    def test_put_image_url_downloads(self):
        rec = RecordingValidate()
        original_urlopen = urllib.request.urlopen

        def fake_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else req
            if isinstance(url, str) and url.startswith(f"http://127.0.0.1:"):
                return original_urlopen(req, *args, **kwargs)
            mock_resp = unittest.mock.MagicMock()
            mock_resp.read.return_value = PNG_1X1
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = False
            return mock_resp

        with self._patch_validate(rec), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"url": "https://example.com/foo.png"}).encode("utf-8")
            status, _h, resp = http_request(
                port, "PUT", "/api/quizzes/test-quiz/entries/person-1/image",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(resp)["image_path"].startswith("images/person-1"))

    def test_put_image_400_on_non_http_url(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"url": "ftp://nope"}).encode("utf-8")
            status, _h, _b = http_request(
                port, "PUT", "/api/quizzes/test-quiz/entries/person-1/image",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 400)

    def test_put_image_404_when_entry_not_found(self):
        original_urlopen = urllib.request.urlopen

        def fake_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else req
            if isinstance(url, str) and url.startswith(f"http://127.0.0.1:"):
                return original_urlopen(req, *args, **kwargs)
            mock_resp = unittest.mock.MagicMock()
            mock_resp.read.return_value = PNG_1X1
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = False
            return mock_resp

        with start_test_server(self.tmp_root, self.admin) as (_s, port), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            body = json.dumps({"url": "https://example.com/x.png"}).encode("utf-8")
            status, _h, _b = http_request(
                port, "PUT", "/api/quizzes/test-quiz/entries/nonexistent/image",
                body=body, headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 404)

    def test_put_image_multipart_saves_upload(self):
        rec = RecordingValidate()
        boundary = "----TestBoundary12345"
        body_parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="image"; filename="upload.png"\r\n',
            b"Content-Type: image/png\r\n\r\n",
            PNG_1X1,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        body = b"".join(body_parts)
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, resp = http_request(
                port, "PUT", "/api/quizzes/test-quiz/entries/person-1/image",
                body=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(body)),
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(resp)["image_path"], "images/person-1.png")

    def test_refetch_runs_fetcher_force_mode(self):
        rec = RecordingValidate()

        class FakeFetch:
            calls: list[dict] = []

            @classmethod
            def fetch_one(cls, entry, list_path, force, user_agent, source):
                cls.calls.append({"entry_id": entry.get("id"), "force": force, "source": source})
                entry["fetch_status"] = "ok"
                return entry

        with self._patch_validate(rec), \
             patch.object(self.admin, "get_fetch_module", return_value=FakeFetch), \
             start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _resp = http_request(port, "POST", "/api/quizzes/test-quiz/entries/person-1/refetch")
            self.assertEqual(status, 200)
            self.assertEqual(len(FakeFetch.calls), 1)
            self.assertTrue(FakeFetch.calls[0]["force"])
            self.assertEqual(FakeFetch.calls[0]["source"], "auto")

    def test_refetch_404_when_entry_not_found(self):
        with start_test_server(self.tmp_root, self.admin) as (_s, port):
            status, _h, _b = http_request(port, "POST", "/api/quizzes/test-quiz/entries/nope/refetch")
            self.assertEqual(status, 404)

    def test_validate_called_after_mutation(self):
        rec = RecordingValidate()
        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            body = json.dumps({"name": "x", "category": "y", "id": "x-1"}).encode("utf-8")
            http_request(port, "POST", "/api/quizzes/test-quiz/entries", body=body,
                         headers={"Content-Type": "application/json"})
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(rec.calls[0][0], "--quiz-dir")
        self.assertIn("test-quiz", rec.calls[0][1])

    def test_concurrent_writes_serialized(self):
        rec = RecordingValidate()
        results: list[int] = []
        results_lock = threading.Lock()

        def worker(idx, port):
            body = json.dumps({"name": f"concurrent-{idx}", "category": "t", "id": f"c-{idx}"}).encode("utf-8")
            try:
                status, _h, _b = http_request(
                    port, "POST", "/api/quizzes/test-quiz/entries",
                    body=body, headers={"Content-Type": "application/json"},
                )
                with results_lock:
                    results.append(status)
            except Exception:
                with results_lock:
                    results.append(0)

        with self._patch_validate(rec), start_test_server(self.tmp_root, self.admin) as (_s, port):
            threads = [threading.Thread(target=worker, args=(i, port)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertEqual(sorted(results), [201, 201, 201, 201, 201])
        list_path = self.tmp_root / "data" / "quizzes" / "test-quiz" / "list.jsonl"
        ids = [json.loads(l)["id"] for l in list_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        for i in range(5):
            self.assertIn(f"c-{i}", ids)


if __name__ == "__main__":
    unittest.main()
