---
name: celeb-quiz-setup
description: >
  Validate a celeb-quiz list.jsonl and build the quiz.json + index.json
  manifests so the web app can discover and load the quiz. Use when the user
  says "퀴즈 데이터 등록", "celeb-quiz 매니페스트 생성", "build celeb quiz manifest",
  "wire up celebrity quiz", "퀴즈 검증", "quiz validate", or after fetching
  images via celeb-quiz-image and ready to publish the quiz to the web app.
metadata:
  version: "1.0.0"
---

# Celeb Quiz — Setup Skill

## When to use

Run this skill whenever you need to validate a quiz's `list.jsonl` and produce
the manifest files the web app reads. The typical flow is: listup → image →
**setup**. But you can also run it standalone on any hand-edited `list.jsonl`.

Trigger phrases:

- "퀴즈 데이터 등록"
- "celeb-quiz 매니페스트 생성"
- "build celeb quiz manifest"
- "wire up celebrity quiz"
- "퀴즈 검증"
- "quiz validate"
- "이미지 다 받았어, 이제 등록해줘"
- "publish quiz to web app"

**Prerequisite:** `data/quizzes/<slug>/list.jsonl` must exist. Images are
typically fetched first via `celeb-quiz-image`, but the validator runs fine
without them (entries without images simply don't count toward `valid_count`).

## What it does

- Parses `list.jsonl` line-by-line, skipping blank lines. Fails immediately on
  malformed JSON and reports the exact line number.
- Validates required fields (`id`, `name`, `category`) and checks that `id`
  matches `^[a-z0-9][a-z0-9-]{0,59}$` and is unique within the file.
- Computes `valid_count`: entries where `fetch_status == "ok"` **and** the
  `image_path` file actually exists on disk.
- Writes `<quiz-dir>/quiz.json` atomically (via `.tmp` + `os.replace`),
  preserving the original `created_at` timestamp on re-runs.
- Rebuilds `data/quizzes/index.json` by scanning all sibling quiz dirs that
  contain a `quiz.json`, sorted by name.

## How to invoke

### From the agent

```bash
python3 .agents/skills/celeb-quiz-setup/scripts/validate.py \
  --quiz-dir data/quizzes/<slug>
```

Run from the repo root. The script has no pip dependencies.

### CLI flags

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--quiz-dir <path>` | yes | — | Quiz directory containing `list.jsonl`. |
| `--title "..."` | no | humanized dir name | Override the display title (e.g. `"한국 야구선수 퀴즈"`). |
| `--countdown N` | no | `7` | Default countdown seconds. Must be 3..60. |
| `--strict` | no | off | Exit 2 if any entry has a non-ok status or missing image. Use in CI. |

## Output files

- **`<quiz-dir>/quiz.json`** — per-quiz manifest. The web app reads this to
  display the quiz card and load `list.jsonl` at runtime. Full schema in
  [`references/manifest-schema.md`](references/manifest-schema.md).
- **`data/quizzes/index.json`** — top-level discovery file. `index.html` fetches
  this first to build the quiz picker. Rebuilt from disk state every run.

## Exit codes & how the agent reacts

| Code | Meaning | Agent action |
|------|---------|--------------|
| 0 | Valid | Proceed; report success to user. |
| 1 | Malformed JSONL or missing required field | Show stderr line numbers; ask user to correct manually OR re-run celeb-quiz-listup. |
| 2 | Strict mode failed (non-ok entries / missing images) | Suggest re-running celeb-quiz-image with `--force`, or omit `--strict` to continue. |
| 3 | Quiz dir missing / no list.jsonl | Verify the slug; suggest running celeb-quiz-listup first. |

## After setup completes

Start the local server and open the app:

```bash
bash scripts/serve.sh
# then open http://localhost:8000/web/
```

Click the new quiz card in the picker, set your countdown, and click Start. The
Player window opens in a new tab. Drag it to the second monitor and press F11
(or Cmd-Ctrl-F on macOS) for fullscreen.

## Idempotent re-runs

Running the script twice is safe. `created_at` is preserved from the first run;
only `updated_at` advances. `index.json` is always rebuilt fresh from whatever
`quiz.json` files exist on disk at that moment.

## Hand-edited list.jsonl is OK

Users can edit `list.jsonl` directly — fix a name typo, drop an entry, add a
missing `id`. Just re-run `validate.py` afterward to refresh both manifests. The
validator doesn't require the file to have come from `celeb-quiz-listup`.

## See also

- [`references/manifest-schema.md`](references/manifest-schema.md) — full field
  tables and examples for `quiz.json` and `index.json`.
- [`scripts/validate.py`](scripts/validate.py) — the script this skill wraps.
  Read the module docstring and `main()` for authoritative behavior.
