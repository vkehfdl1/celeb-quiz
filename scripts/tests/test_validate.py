"""Offline tests for the celeb-quiz setup validator.

Run from the repository root with:
    python3 -m unittest scripts.tests.test_validate -v

The validator lives under .agents/skills/celeb-quiz-setup/scripts, so this test
module imports it by file path. All disk I/O stays inside TemporaryDirectory.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
VALIDATE_PATH = ROOT / ".agents" / "skills" / "celeb-quiz-setup" / "scripts" / "validate.py"


def load_validate_module():
    spec = importlib.util.spec_from_file_location("celeb_quiz_validate", VALIDATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate = load_validate_module()


def write_jsonl(path: Path, entries: list[dict], *, blank_between: bool = False) -> None:
    separator = "\n\n" if blank_between else "\n"
    content = separator.join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n"
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ValidateTests(unittest.TestCase):
    def make_quiz(self, root: Path, name: str = "korean-baseball") -> Path:
        quiz_dir = root / "data" / "quizzes" / name
        (quiz_dir / "images").mkdir(parents=True)
        return quiz_dir

    def run_main(self, *args: str) -> tuple[int, str]:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = validate.main(list(args))
        return code, stderr.getvalue()

    def write_ok_entries(self, quiz_dir: Path, count: int = 3) -> list[dict]:
        entries = []
        for index in range(count):
            image_path = f"images/player-{index}.jpg"
            (quiz_dir / image_path).write_bytes(b"fake")
            entries.append(
                {
                    "id": f"player-{index}",
                    "name": f"선수 {index}",
                    "category": "야구선수",
                    "fetch_status": "ok",
                    "image_path": image_path,
                }
            )
        write_jsonl(quiz_dir / "list.jsonl", entries)
        return entries

    def test_humanize_name(self):
        self.assertEqual(validate.humanize_name("example-historical-figures"), "Example Historical Figures")
        self.assertEqual(validate.humanize_name("korean-baseball"), "Korean Baseball")

    def test_id_format_valid(self):
        for slug in ["a", "lee-jung-hoo", "abc123", "a-1-b", "x" * 60]:
            with self.subTest(slug=slug):
                self.assertTrue(validate.validate_id(slug))

    def test_id_format_invalid(self):
        for slug in ["", "Lee", "-lee", "lee_", "lee jung", "x" * 61, "한글"]:
            with self.subTest(slug=slug):
                self.assertFalse(validate.validate_id(slug))

    def test_valid_quiz(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(validate, "_now", return_value="2026-04-30T12:00:00Z"):
            quiz_dir = self.make_quiz(Path(tmp))
            self.write_ok_entries(quiz_dir, 3)

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir), "--title", "한국 야구선수 퀴즈")

            self.assertEqual(code, 0, stderr)
            quiz = read_json(quiz_dir / "quiz.json")
            self.assertEqual(quiz["schema_version"], 1)
            self.assertEqual(quiz["name"], "korean-baseball")
            self.assertEqual(quiz["title"], "한국 야구선수 퀴즈")
            self.assertEqual(quiz["category"], "야구선수")
            self.assertEqual(quiz["count"], 3)
            self.assertEqual(quiz["valid_count"], 3)
            self.assertEqual(quiz["default_countdown_seconds"], 7)
            self.assertEqual(quiz["list_path"], "list.jsonl")
            self.assertEqual(quiz["created_at"], "2026-04-30T12:00:00Z")
            self.assertEqual(quiz["updated_at"], "2026-04-30T12:00:00Z")
            self.assertEqual(quiz["generator"], {"setup_skill_version": "1.0.0"})

    def test_missing_required_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            write_jsonl(quiz_dir / "list.jsonl", [{"id": "lee", "name": "이"}])

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 1)
            self.assertIn("Line 1", stderr)
            self.assertIn("category", stderr)

    def test_duplicate_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            write_jsonl(
                quiz_dir / "list.jsonl",
                [
                    {"id": "same", "name": "A", "category": "야구선수"},
                    {"id": "same", "name": "B", "category": "야구선수"},
                ],
            )

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 1)
            self.assertIn("Line 2", stderr)
            self.assertIn("Line 1", stderr)

    def test_invalid_id_format(self):
        for bad_id in ["Lee", "-lee"]:
            with self.subTest(bad_id=bad_id), tempfile.TemporaryDirectory() as tmp:
                quiz_dir = self.make_quiz(Path(tmp))
                write_jsonl(quiz_dir / "list.jsonl", [{"id": bad_id, "name": "A", "category": "야구선수"}])

                code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

                self.assertEqual(code, 1)
                self.assertIn("Line 1", stderr)

    def test_image_missing_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            write_jsonl(
                quiz_dir / "list.jsonl",
                [{"id": "lee", "name": "이", "category": "야구선수", "fetch_status": "ok", "image_path": "images/missing.jpg"}],
            )

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))
            self.assertEqual(code, 0, stderr)
            self.assertEqual(read_json(quiz_dir / "quiz.json")["valid_count"], 0)
            self.assertIn("missing", stderr.lower())

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir), "--strict")
            self.assertEqual(code, 2)
            self.assertIn("missing", stderr.lower())

    def test_fetch_status_not_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            write_jsonl(
                quiz_dir / "list.jsonl",
                [{"id": "lee", "name": "이", "category": "야구선수", "fetch_status": "no_free_image"}],
            )

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 0, stderr)
            self.assertEqual(read_json(quiz_dir / "quiz.json")["valid_count"], 0)

    def test_atomic_write_preserves_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            self.write_ok_entries(quiz_dir, 1)
            original = {"schema_version": 1, "created_at": "2025-01-01T00:00:00Z", "sentinel": True}
            (quiz_dir / "quiz.json").write_text(json.dumps(original), encoding="utf-8")

            with patch.object(validate.os, "replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    validate.main(["--quiz-dir", str(quiz_dir)])

            self.assertEqual(read_json(quiz_dir / "quiz.json"), original)
            self.assertFalse((quiz_dir / "quiz.json.tmp").exists())

    def test_index_json_built(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha = self.make_quiz(root, "alpha-quiz")
            beta = self.make_quiz(root, "beta-quiz")
            self.write_ok_entries(alpha, 1)
            self.write_ok_entries(beta, 2)
            self.run_main("--quiz-dir", str(beta), "--title", "Beta Quiz")

            code, stderr = self.run_main("--quiz-dir", str(alpha), "--title", "Alpha Quiz")

            self.assertEqual(code, 0, stderr)
            index = read_json(root / "data" / "quizzes" / "index.json")
            self.assertEqual([item["name"] for item in index["quizzes"]], ["alpha-quiz", "beta-quiz"])
            self.assertEqual(index["quizzes"][0]["title"], "Alpha Quiz")
            self.assertEqual(index["quizzes"][1]["valid_count"], 2)

    def test_index_json_skips_dirs_without_quiz_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quiz_dir = self.make_quiz(root, "real-quiz")
            skipped = root / "data" / "quizzes" / "draft-quiz"
            skipped.mkdir(parents=True)
            self.write_ok_entries(quiz_dir, 1)

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 0, stderr)
            names = [item["name"] for item in read_json(root / "data" / "quizzes" / "index.json")["quizzes"]]
            self.assertEqual(names, ["real-quiz"])

    def test_created_at_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(validate, "_now", side_effect=["2026-04-30T12:00:00Z", "2026-04-30T12:00:01Z"]):
            quiz_dir = self.make_quiz(Path(tmp))
            self.write_ok_entries(quiz_dir, 1)
            (quiz_dir / "quiz.json").write_text(
                json.dumps({"created_at": "2025-01-01T00:00:00Z"}, ensure_ascii=False),
                encoding="utf-8",
            )

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 0, stderr)
            quiz = read_json(quiz_dir / "quiz.json")
            self.assertEqual(quiz["created_at"], "2025-01-01T00:00:00Z")
            self.assertEqual(quiz["updated_at"], "2026-04-30T12:00:00Z")

    def test_countdown_range(self):
        for countdown, should_pass in [(2, False), (7, True), (60, True), (61, False)]:
            with self.subTest(countdown=countdown), tempfile.TemporaryDirectory() as tmp:
                quiz_dir = self.make_quiz(Path(tmp))
                self.write_ok_entries(quiz_dir, 1)

                code, stderr = self.run_main("--quiz-dir", str(quiz_dir), "--countdown", str(countdown))

                if should_pass:
                    self.assertEqual(code, 0, stderr)
                    self.assertEqual(read_json(quiz_dir / "quiz.json")["default_countdown_seconds"], countdown)
                else:
                    self.assertNotEqual(code, 0)
                    self.assertIn("countdown", stderr.lower())

    def test_jsonl_blank_lines_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            (quiz_dir / "images" / "one.jpg").write_bytes(b"fake")
            write_jsonl(
                quiz_dir / "list.jsonl",
                [{"id": "one", "name": "One", "category": "위인", "fetch_status": "ok", "image_path": "images/one.jpg"}],
                blank_between=True,
            )

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 0, stderr)
            self.assertEqual(read_json(quiz_dir / "quiz.json")["count"], 1)

    def test_jsonl_parse_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            quiz_dir = self.make_quiz(Path(tmp))
            (quiz_dir / "list.jsonl").write_text('{"id": "ok", "name": "A", "category": "B"}\n{bad json}\n', encoding="utf-8")

            code, stderr = self.run_main("--quiz-dir", str(quiz_dir))

            self.assertEqual(code, 1)
            self.assertIn("Line 2", stderr)


if __name__ == "__main__":
    unittest.main()
