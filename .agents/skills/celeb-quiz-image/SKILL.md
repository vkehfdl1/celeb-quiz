---
name: celeb-quiz-image
description: >
  Fetch free-licensed Wikipedia/Wikimedia photos for celeb-quiz list.jsonl
  entries. Use when the user says "퀴즈 인물 사진 가져오기", "celeb-quiz 사진",
  "fetch celebrity quiz images", "wikipedia photos for quiz", "사진 자동 수집",
  "위키 사진 다운로드", or after running celeb-quiz-listup and ready to
  populate images. Operates on a list.jsonl file produced by celeb-quiz-listup.
metadata:
  version: "1.0.0"
---

# Celeb Quiz — Image Fetch Skill

## When to use

Run this skill after `celeb-quiz-listup` has produced a `list.jsonl` file. The
file must already exist with at least `id`, `name`, and `category` fields per
entry. This skill enriches those entries with image data and writes the results
back in-place.

Trigger phrases:

- "퀴즈 인물 사진 가져오기"
- "celeb-quiz 사진"
- "fetch celebrity quiz images"
- "wikipedia photos for quiz"
- "사진 자동 수집"
- "위키 사진 다운로드"
- "이미지 수집해줘"
- "사진 채워줘"

## What it does

- Reads each entry's `name` (and optional `disambiguation`) and searches
  `ko.wikipedia.org` first, then `en.wikipedia.org` as a fallback.
- Pulls the page's representative image via `prop=pageimages&pilicense=free`,
  which restricts results to CC and Public Domain images server-side.
- Resolves full attribution metadata (artist, license name, license URL) via
  the Wikimedia Commons `imageinfo` extmetadata API.
- Downloads the image to `<quiz-dir>/images/<id>.<ext>` and rewrites
  `list.jsonl` atomically with all enrichment fields populated.

## How to invoke

### From the agent

Run the bundled script via Bash from the repository root:

```bash
python3 .agents/skills/celeb-quiz-image/scripts/fetch.py data/quizzes/<slug>/list.jsonl
```

The script writes per-entry progress to stderr and ends with a summary line:

```
[summary] processed=N ok=X not_found=Y no_free_image=Z too_small=W error=E
```

**Always surface this summary line to the user.**

### CLI options

| Flag | Effect |
|------|--------|
| `--force` | Re-fetch entries that already have `fetch_status=ok`. Use after editing `list.jsonl` or renaming entries. |
| `--limit N` | Process only the first N entries. Good for a spot-check before committing to a full batch. |
| `--user-agent UA` | Override the Wikimedia User-Agent header. Rarely needed; the default is correct. |

Example spot-check:

```bash
python3 .agents/skills/celeb-quiz-image/scripts/fetch.py \
  data/quizzes/kbo-players/list.jsonl --limit 5
```

## Result handling

After the script exits, parse the summary line and act on each counter:

**`error > 0`** — suggest re-running with `--limit` to isolate the failing
entries, or inspect the stderr log for the specific error message. Common causes
are network timeouts and malformed API responses. Use `--force` once the issue
is resolved.

**`not_found` or `no_free_image`** — present the user with three options:
1. Add a more specific `disambiguation` field to the entry in `list.jsonl`
   (e.g., `"disambiguation": "야구선수"`), then re-run with `--force`.
2. Accept the gap. Some celebrities genuinely have no free image on Wikipedia.
3. Drop the entry from `list.jsonl` if a photo is required for the quiz to work.

**`too_small`** — the page exists but its lead image is a tiny thumbnail (both
dimensions under 400 px). Suggest manual intervention: check the Wikipedia page
directly and, if a better image exists under a free license, note the Commons
filename in `disambiguation` or drop the entry.

After handling exceptions, render a summary table for the user:

| id | name | fetch_status | license |
|----|------|-------------|---------|
| jung-hoo-lee | 이정후 | ok | CC BY-SA 4.0 |
| ... | ... | ... | ... |

## Re-runs are idempotent

By default, any entry where `fetch_status == "ok"` **and** the image file
exists on disk is skipped without a network call. This makes re-runs safe and
fast after partial failures.

Use `--force` to override — for example, after manually renaming an entry's
`id` (which also requires renaming the image file per AGENTS.md §4) or after a
license re-check.

## License policy

**Non-negotiable.** Only `Public Domain`, `CC0`, `CC-BY`, and `CC-BY-SA`
images may be saved. The script enforces this via `pilicense=free` at the API
level and then verifies `LicenseShortName` from Commons extmetadata.

**Never** source images from Google Images, Bing, Naver, or any non-Wikimedia
source through this skill. **Never** manually add an `image_path` to
`list.jsonl` for a non-free image.

See [`references/license-policy.md`](references/license-policy.md) for the
full policy, including attribution display requirements.

## Hand-off

Once the fetch run completes with acceptable results, run the setup skill to
validate the quiz directory and build the manifest:

```bash
python3 .agents/skills/celeb-quiz-setup/scripts/validate.py \
  --quiz-dir data/quizzes/<slug>
```

If `validate.py` exits non-zero, fix the reported issues before proceeding.

## Troubleshooting

**HTTP 429 storm** — the script auto-retries with exponential backoff (1 s, 2 s,
4 s, 8 s, 16 s) up to 5 attempts per request. If all retries fail, the entry is
marked `error`. Wait a few minutes, then re-run with `--force` for those entries.

**Korean name resolves to the wrong person** — e.g., "이정수" matches a
different person than intended. Set the `disambiguation` field in `list.jsonl`:

```json
{"id": "jeong-su-lee", "name": "이정수", "disambiguation": "축구선수", ...}
```

Then re-run with `--force`.

**Network offline** — all entries become `error`. Verify connectivity, then
re-run with `--force`.

**Image too small** — the script rejects images where both `original.width` and
`original.height` are under 400 px. If the Wikipedia page has a larger image
available, it may be under a non-free license (and correctly excluded). Accept
the gap or drop the entry.

## See also

- [`references/wikimedia-api.md`](references/wikimedia-api.md) — exact API
  endpoints, parameters, and response shapes used by the script.
- [`references/license-policy.md`](references/license-policy.md) — full license
  policy with attribution requirements.
- [`scripts/fetch.py`](scripts/fetch.py) — the implementation. The module
  docstring and function docstrings are the authoritative source of truth.
