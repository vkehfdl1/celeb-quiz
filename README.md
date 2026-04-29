# celeb-quiz

> Self-hosted, agent-native person/celebrity photo quiz.

A minimal local web app that runs a "guess the person from the photo" quiz across
two screens — a host control screen and an extension-monitor player screen. Quiz
content (person lists + their representative photos) is curated by three
[Vercel Agent Skills](https://vercel.com/docs/agent-resources/skills), so adding
a new quiz is a conversation with your coding agent, not a manual data-entry
chore.

```
┌────────────── Vercel Agent Skills ─────────────┐    ┌──── data/ ────┐    ┌──── web/ ────┐
│                                                │    │               │    │              │
│  celeb-quiz-listup  →  list.jsonl              │ →  │  list.jsonl   │ →  │  index.html  │
│  celeb-quiz-image   →  images/ + enriched JSONL│    │  images/*.jpg │    │  host.html   │
│  celeb-quiz-setup   →  quiz.json + index.json  │    │  quiz.json    │    │  player.html │
│                                                │    │  index.json   │    │              │
└────────────────────────────────────────────────┘    └───────────────┘    └──────────────┘
```

## Quick start

```bash
git clone https://github.com/vkehfdl1/celeb-quiz.git
cd celeb-quiz

bash scripts/serve.sh        # macOS / Linux
scripts\serve.bat            # Windows
```

Open `http://localhost:8000/web/` in your primary browser. Pick the bundled
`example-historical-figures` quiz, set a countdown, and click **Start**.

A second browser window (the **player**) pops up. Drag it to your second monitor
and press **F11** for fullscreen. The first window remains the **host** — that's
where you control the game.

| Key | Action |
|-----|--------|
| `Space` | Next person |
| `R` | Reveal answer |
| `Esc` | Restart (re-shuffle queue) |

## How it works

The skills live under `.agents/skills/` and follow the
[Vercel Agent Skills](https://vercel.com/docs/agent-resources/skills) spec
(SKILL.md frontmatter + optional `scripts/` and `references/`). Any agent
runtime that supports the spec — Claude Code, Cursor, OpenCode, Vercel — can
load them and trigger them by phrase.

### 1. `celeb-quiz-listup` — interview-style person curation

Trigger phrases: *"퀴즈 인물 목록 만들기", "list up celebrities for quiz",
"야구선수 퀴즈 만들어줘"*.

The agent asks for a category (야구선수, K-pop 아이돌, 위인, 정치인, 헐리우드 배우,
…), a target count, and a quiz slug, then proposes candidates in batches of 10.
You review each batch — strike out the unknowns, swap names you'd rather have —
before the agent appends them to `data/quizzes/<slug>/list.jsonl`.

The skill carries a romanization rule book
([`references/category-examples.md`](./.agents/skills/celeb-quiz-listup/references/category-examples.md))
so Korean names get clean kebab-case `id` fields like `lee-jung-hoo` and
`yi-sun-sin`.

### 2. `celeb-quiz-image` — Wikipedia / web photo fetch

Trigger phrases: *"퀴즈 인물 사진 가져오기", "fetch celebrity quiz images",
"위키 사진 다운로드"*.

The skill wraps a small Python script (`scripts/fetch.py`, urllib stdlib only)
that defaults to a publishable Wikimedia-only mode:

- searches `ko.wikipedia.org` first, falls back to `en.wikipedia.org`
- pulls the page's representative image via `prop=pageimages&pilicense=free`
- resolves attribution from Wikimedia Commons `imageinfo` extmetadata
- downloads the original to `<quiz-dir>/images/<id>.<ext>`
- atomically rewrites `list.jsonl` with full enrichment fields

For private/non-commercial gatherings, `--source wiki-any` drops the Wikimedia
free-license filter and `--source auto` tries `wiki-free → wiki-any →
DuckDuckGo → Bing`. Those modes may save unknown/non-free images and are not
safe to redistribute.

```bash
python3 .agents/skills/celeb-quiz-image/scripts/fetch.py \
  data/quizzes/<slug>/list.jsonl
```

Useful flags: `--force` (re-fetch already-ok entries), `--limit N`
(spot-check first N), `--source wiki-free|wiki-any|auto`, and
`--allow-non-free` (alias for `--source auto`).

### 3. `celeb-quiz-setup` — validate + manifest builder

Trigger phrases: *"퀴즈 데이터 등록", "build celeb quiz manifest",
"wire up celebrity quiz"*.

Wraps `scripts/validate.py` which validates the JSONL schema (required fields,
`id` regex, uniqueness), counts `valid_count`, writes per-quiz `quiz.json`
atomically (preserves `created_at`), and rebuilds top-level
`data/quizzes/index.json`.

```bash
python3 .agents/skills/celeb-quiz-setup/scripts/validate.py \
  --quiz-dir data/quizzes/<slug> \
  --title "한국 야구선수 퀴즈" \
  --countdown 7
```

Pass `--strict` in CI to fail on any non-ok entry.

## Adding a new quiz manually

If you'd rather skip the agent and hand-author a quiz:

1. Create `data/quizzes/<slug>/list.jsonl`. Required fields per line:
   ```json
   {"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}
   ```
   The `id` must match `^[a-z0-9][a-z0-9-]{0,59}$` and be unique within the
   file. See
   [`jsonl-schema.md`](./.agents/skills/celeb-quiz-listup/references/jsonl-schema.md)
   for the full schema.

2. Run the image fetcher, then the validator.

3. Refresh `http://localhost:8000/web/` — your quiz appears in the picker.

## Dual-monitor setup

The web app uses the
[BroadcastChannel API](https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel)
to sync the host and player windows. No Electron, no websocket server — just
two pages talking inside the browser.

1. Click **Start** on `index.html`. The current tab navigates to `host.html`
   and a popup window opens with `player.html`.
2. Drag the player window onto your extension monitor.
3. Press **F11** (Windows/Linux) or **Cmd-Ctrl-F** (macOS) in the player
   window to fullscreen it.
4. Run the quiz from the host. The player mirrors photo, countdown, "땡!", and
   reveal events live.

If the player window gets closed accidentally, click **Reopen Player ↗** on the
host. Both windows share a channel name derived from the quiz slug, so the
reopened popup picks up the in-progress session immediately.

## Image source policy

By default, this project stores only free-licensed images. The fetcher enforces
this server-side via Wikimedia's `pilicense=free` filter, and the player UI
always shows attribution in the bottom-right corner — both legally and
aesthetically required for CC-BY content. This default mode is the only mode
safe for publishing or redistributing quiz data.

| Allowed | Forbidden |
|---------|-----------|
| Public domain | All rights reserved |
| CC0 | Fair use |
| CC-BY (with attribution) | NC (NonCommercial) |
| CC-BY-SA (with attribution) | ND (NoDerivs) |

For private/non-commercial events, `--source wiki-any`, `--source auto`, or
`--allow-non-free` can fetch images with unknown/non-free copyright status.
Do not publish, redistribute, or use those fetched `data/` directories
commercially; the repo MIT license covers the code, not non-free images.

## Development

### Python tests (stdlib `unittest`, no pip)

```bash
python3 -m unittest discover scripts/tests -v
```

Runs the fetcher + validator unit suites — 28 tests, all offline (network calls
are mocked).

### Browser tests (open in browser, no Node)

```bash
bash scripts/serve.sh
# then open http://localhost:8000/web/tests/test.html
```

The page renders pass/fail boxes for `shuffle`, `quiz-loader`, and `sync`
modules. No build step, no test runner — just `<script type="module">`.

### Project layout

```
.agents/skills/        Vercel Agent Skills (SKILL.md + scripts/ + references/)
data/quizzes/          Per-quiz data (list.jsonl + quiz.json + images/)
scripts/               Cross-cutting helpers (serve.sh, tests/)
web/                   Vanilla HTML/CSS/JS quiz app
```

Project rules — schema invariants, naming, license policy, atomic-commit
discipline — live in [AGENTS.md](./AGENTS.md). Read that before making
changes.

## Stack constraints

- **Web app**: zero npm dependencies. Vanilla HTML/CSS/JS, ES modules, served
  by `python3 -m http.server`. No build step, no transpiler, no framework.
- **Python scripts**: zero pip dependencies. `urllib`, `json`, `hashlib`,
  `pathlib`, `argparse`, `unittest` — all stdlib.
- **Cross-platform**: macOS, Windows, Linux. Verified BroadcastChannel works
  on Safari 15.4+, Chrome, Firefox.

## License

[MIT](./LICENSE) — Copyright © 2026 vkehfdl1.

## Acknowledgements

- [Wikipedia](https://www.wikipedia.org) and
  [Wikimedia Commons](https://commons.wikimedia.org) for the open photo
  archive that makes this whole thing possible.
- [Vercel Agent Skills](https://vercel.com/docs/agent-resources/skills) for
  the portable, agent-native skill format.
