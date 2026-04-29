# Manifest Schema Reference

Output schemas produced by `validate.py` (celeb-quiz-setup v1.0.0).

---

## `<quiz-dir>/quiz.json`

Written atomically on every successful run. The web app reads this file to
display the quiz card and know where to load `list.jsonl` from.

### Fields

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `schema_version` | int | constant | Currently `1`. Bumped on breaking changes. |
| `name` | string | quiz dir basename | Used as the quiz id in `index.json`. |
| `title` | string | `--title` or humanized name | Display title in the web app picker. |
| `category` | string | mode of entries' category | Most-common category from `list.jsonl`. Ties broken alphabetically. |
| `count` | int | computed | Total entries in `list.jsonl` (blank lines excluded). |
| `valid_count` | int | computed | Entries with `fetch_status == "ok"` AND `image_path` present on disk. |
| `default_countdown_seconds` | int | `--countdown` (default 7) | Default n for the countdown timer; user can override per session. |
| `list_path` | string | constant `"list.jsonl"` | Relative path the web app reads at runtime. |
| `created_at` | ISO 8601 string | preserved if present | First-build timestamp. Not updated on re-runs. |
| `updated_at` | ISO 8601 string | always now | Last-build timestamp. Always the current UTC time. |
| `generator.setup_skill_version` | string | constant `"1.0.0"` | Provenance trail for debugging. |

### Example

```json
{
  "schema_version": 1,
  "name": "kbo-players",
  "title": "한국 야구선수 퀴즈",
  "category": "야구선수",
  "count": 50,
  "valid_count": 47,
  "default_countdown_seconds": 7,
  "list_path": "list.jsonl",
  "created_at": "2026-04-01T09:00:00Z",
  "updated_at": "2026-04-30T14:22:11Z",
  "generator": {
    "setup_skill_version": "1.0.0"
  }
}
```

---

## `data/quizzes/index.json`

Rebuilt from disk on every run by scanning all sibling quiz dirs that contain a
`quiz.json`. The web app's `index.html` fetches this file first to populate the
quiz picker.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Currently `1`. |
| `quizzes[]` | array | One entry per discovered quiz dir with a `quiz.json`. Sorted by `name` ASC. |
| `quizzes[].name` | string | Same as `name` in the per-quiz manifest. |
| `quizzes[].title` | string | Display title. |
| `quizzes[].count` | int | Total entries. |
| `quizzes[].valid_count` | int | Image-ready entries. |
| `quizzes[].category` | string | Same as `category` in `quiz.json`. |
| `updated_at` | ISO 8601 string | Timestamp of the last index rebuild. |

### Example (two quizzes)

```json
{
  "schema_version": 1,
  "quizzes": [
    {
      "name": "example-historical-figures",
      "title": "Example Historical Figures",
      "count": 10,
      "valid_count": 8,
      "category": "역사인물"
    },
    {
      "name": "kbo-players",
      "title": "한국 야구선수 퀴즈",
      "count": 50,
      "valid_count": 47,
      "category": "야구선수"
    }
  ],
  "updated_at": "2026-04-30T14:22:11Z"
}
```

---

## `list.jsonl` schema (cross-reference)

`list.jsonl` is the **input** to `validate.py`, not an output. For the full
field specification see `celeb-quiz-listup`'s
`references/jsonl-schema.md`.

### Required fields (validated by this skill)

| Field | Type | Validation rule |
|-------|------|----------------|
| `id` | string | Must match `^[a-z0-9][a-z0-9-]{0,59}$`. Must be unique within the file. |
| `name` | string | Non-empty string. Display name (Korean OK). |
| `category` | string | Non-empty string. Group label (e.g. `야구선수`). |

### Format rules

- One JSON object per line (JSON Lines / NDJSON).
- Blank lines are silently skipped.
- No enclosing array, no trailing commas.
- UTF-8 encoding required.
- Malformed JSON on any non-blank line causes exit code 1 with the line number
  reported to stderr.
