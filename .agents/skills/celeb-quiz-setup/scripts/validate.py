"""Validate celeb-quiz JSONL data and build quiz manifests.

Usage:
    python3 validate.py --quiz-dir data/quizzes/example-historical-figures

The script performs offline validation only: no network requests and no third-
party dependencies. It writes quiz.json and data/quizzes/index.json atomically.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


SETUP_SKILL_VERSION = "1.0.0"
FETCH_STATUSES = {"ok", "not_found", "no_free_image", "too_small", "error"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")


class ValidationError(Exception):
    """Blocking validation error with a process exit code."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def humanize_name(name: str) -> str:
    """Convert a kebab-case quiz directory name to a display title."""

    return " ".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)


def validate_id(value: str) -> bool:
    """Return True when value is a valid kebab-case ASCII entry id."""

    return bool(ID_RE.fullmatch(value))


def parse_jsonl(list_path: Path) -> list[tuple[int, dict[str, Any]]]:
    """Parse JSON Lines, skipping blank lines and preserving source line numbers."""

    entries: list[tuple[int, dict[str, Any]]] = []
    with list_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"Line {line_number}: {exc.msg}") from exc
            if not isinstance(entry, dict):
                raise ValidationError(f"Line {line_number}: expected JSON object")
            entries.append((line_number, entry))
    return entries


def validate_entries(entries: list[tuple[int, dict[str, Any]]], stderr: TextIO = sys.stderr) -> list[str]:
    """Validate required fields, id format, uniqueness, and status enum.

    Returns non-blocking warning messages. Malformed schema issues raise
    ValidationError immediately.
    """

    warnings: list[str] = []
    first_seen: dict[str, int] = {}
    for line_number, entry in entries:
        for field in ("id", "name", "category"):
            if field not in entry:
                raise ValidationError(f"Line {line_number}: missing required field {field}")
            if not isinstance(entry[field], str):
                raise ValidationError(f"Line {line_number}: field {field} must be a string")

        entry_id = entry["id"]
        if not validate_id(entry_id):
            raise ValidationError(f"Line {line_number}: invalid id format {entry_id!r}")
        if entry_id in first_seen:
            raise ValidationError(f"Line {line_number}: duplicate id {entry_id!r} first seen on Line {first_seen[entry_id]}")
        first_seen[entry_id] = line_number

        if "fetch_status" in entry and entry["fetch_status"] not in FETCH_STATUSES:
            warnings.append(f"Line {line_number}: unknown fetch_status {entry['fetch_status']!r}")

    for warning in warnings:
        print(warning, file=stderr)
    return warnings


def _entry_has_existing_image(quiz_dir: Path, entry: dict[str, Any]) -> bool:
    image_path = entry.get("image_path")
    if not isinstance(image_path, str) or not image_path:
        return False
    return (quiz_dir / image_path).is_file()


def compute_valid_count(quiz_dir: Path, entries: list[tuple[int, dict[str, Any]]]) -> int:
    """Count entries with fetch_status ok and an existing image file."""

    return sum(1 for _, entry in entries if entry.get("fetch_status") == "ok" and _entry_has_existing_image(quiz_dir, entry))


def _collect_runtime_warnings(quiz_dir: Path, entries: list[tuple[int, dict[str, Any]]], stderr: TextIO) -> list[str]:
    warnings: list[str] = []
    for line_number, entry in entries:
        if entry.get("fetch_status") != "ok":
            warnings.append(f"Line {line_number}: fetch_status is not ok")
        if entry.get("fetch_status") == "ok" and not _entry_has_existing_image(quiz_dir, entry):
            warnings.append(f"Line {line_number}: image_path missing on disk")

    categories = [entry["category"] for _, entry in entries]
    category_counts = Counter(categories)
    if len(category_counts) > 1:
        mode_count = category_counts.most_common(1)[0][1]
        tied_modes = [category for category, count in category_counts.items() if count == mode_count]
        if len(tied_modes) == 1:
            warnings.append(f"Multiple categories found; using mode {tied_modes[0]!r}")

    for warning in warnings:
        print(warning, file=stderr)
    return warnings


def _category_mode(entries: list[tuple[int, dict[str, Any]]]) -> str:
    if not entries:
        return ""
    counts = Counter(entry["category"] for _, entry in entries)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _read_existing_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to path via sibling .tmp and os.replace."""

    tmp_path = path.with_name(path.name + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def build_quiz_json(
    quiz_dir: Path,
    entries: list[tuple[int, dict[str, Any]]],
    title: str | None = None,
    countdown: int = 7,
) -> dict[str, Any]:
    """Build the quiz.json payload, preserving created_at when present."""

    existing = _read_existing_json(quiz_dir / "quiz.json")
    timestamp = _now()
    return {
        "schema_version": 1,
        "name": quiz_dir.name,
        "title": title if title is not None else humanize_name(quiz_dir.name),
        "category": _category_mode(entries),
        "count": len(entries),
        "valid_count": compute_valid_count(quiz_dir, entries),
        "default_countdown_seconds": countdown,
        "list_path": "list.jsonl",
        "created_at": existing.get("created_at", timestamp),
        "updated_at": timestamp,
        "generator": {"setup_skill_version": SETUP_SKILL_VERSION},
    }


def rebuild_index_json(quiz_dir: Path) -> dict[str, Any]:
    """Rebuild data/quizzes/index.json by scanning sibling quiz dirs."""

    quizzes_root = quiz_dir.parent
    quizzes: list[dict[str, Any]] = []
    for sibling in quizzes_root.iterdir():
        if not sibling.is_dir():
            continue
        manifest_path = sibling / "quiz.json"
        if not manifest_path.exists():
            continue
        manifest = _read_existing_json(manifest_path)
        if not manifest:
            continue
        quizzes.append(
            {
                "name": manifest.get("name", sibling.name),
                "title": manifest.get("title", humanize_name(sibling.name)),
                "count": manifest.get("count", 0),
                "valid_count": manifest.get("valid_count", 0),
                "category": manifest.get("category", ""),
            }
        )

    quizzes.sort(key=lambda item: item["name"])
    payload = {"schema_version": 1, "quizzes": quizzes, "updated_at": _now()}
    atomic_write_json(quizzes_root / "index.json", payload)
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a celeb-quiz list.jsonl and build quiz manifests.")
    parser.add_argument("--quiz-dir", required=True, help="Path to a quiz directory containing list.jsonl")
    parser.add_argument("--title", help="Override the generated quiz title")
    parser.add_argument("--countdown", type=int, default=7, help="Default countdown seconds, 3 through 60")
    parser.add_argument("--strict", action="store_true", help="Exit 2 for non-ok fetch statuses or missing images")
    args = parser.parse_args(argv)
    if not 3 <= args.countdown <= 60:
        parser.error("--countdown must be in range 3..60")
    return args


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the documented process exit code."""

    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    quiz_dir = Path(args.quiz_dir)
    list_path = quiz_dir / "list.jsonl"
    if not quiz_dir.is_dir() or not list_path.is_file():
        print(f"Quiz dir does not exist or is missing list.jsonl: {quiz_dir}", file=sys.stderr)
        return 3

    try:
        entries = parse_jsonl(list_path)
        validate_entries(entries, sys.stderr)
        warnings = _collect_runtime_warnings(quiz_dir, entries, sys.stderr)
        quiz_payload = build_quiz_json(quiz_dir, entries, args.title, args.countdown)
        atomic_write_json(quiz_dir / "quiz.json", quiz_payload)
        rebuild_index_json(quiz_dir)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    if args.strict and warnings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
