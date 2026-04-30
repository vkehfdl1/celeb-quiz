# AGENTS.md — celeb-quiz project rules

This file is loaded by every coding agent working in this repository.
It supplements (not replaces) the three Vercel Agent Skills under `.agents/skills/`.

## 1. Project shape (do not invent new top-level dirs)

```
.agents/skills/{listup,image,setup}/   Vercel Agent Skills (SKILL.md + scripts/ + references/)
data/quizzes/{quiz-name}/              Per-quiz data: list.jsonl, quiz.json, images/
scripts/                               Cross-cutting helpers (serve.sh, tests/)
web/                                   Vanilla HTML/CSS/JS quiz app (no framework, no build step)
```

## 2. Data schema invariants

`list.jsonl` is **JSON Lines**: one object per line, no enclosing array, no trailing
commas, UTF-8 with `ensure_ascii=False`.

Required fields per entry:

- `id` — kebab-case ASCII slug, unique within the file. Set by the listup skill.
- `name` — display name (Korean OK).
- `category` — group label (e.g., `야구선수`).

Optional / progressively populated fields:

- `name_aliases`, `disambiguation` — set at listup time.
- `image_path`, `image_source_url`, `image_width`, `image_height`, `license`,
  `license_short`, `license_url`, `artist`, `attribution_html`, `wikipedia_title`,
  `wikipedia_url`, `wikipedia_lang`, `fetched_at`, `fetch_status` — set by the image skill.

`quiz.json` is the per-quiz manifest, written by the setup skill.
`data/quizzes/index.json` is the top-level discovery file, also written by setup.

## 3. Image source policy

### Default mode (publishable, share-safe)

- `--source wiki-free` (default): only `Public Domain`, `CC0`, `CC-BY`, `CC-BY-SA` images
  via Wikimedia Commons `pilicense=free`.
- For CC-BY / CC-BY-SA: `artist` and `license_url` MUST be present and the player UI
  always displays attribution.
- This is the only mode safe for sharing the resulting `data/` directory publicly.

### Private/non-commercial mode

- `--source wiki-any`: drops the free-license filter; uses Wikipedia's lead image
  regardless of license.
- `--source auto`: full fallback chain `wiki-free → wiki-any → DuckDuckGo → Bing`.
  Maximizes hit rate but pulls images of unknown copyright status.
- `--allow-non-free`: alias for `--source auto`.

These modes are intended for private gatherings (club MTs, classroom games)
where the resulting quiz is not redistributed. The repo MIT license covers
the code, NOT the images fetched in non-free mode. Do NOT push such `data/`
directories to a public repo or use commercially.

## 4. Naming & slug rules

- File slugs: lowercase ASCII, words separated by `-` (kebab-case). Max 60 chars.
- Korean names → the listup skill sets a romanized `id` field. The image skill uses
  `id` directly as the image filename slug. If `id` is missing, fall back to a
  10-char SHA1 hash of the UTF-8 name.
- Image extensions: keep the original from Wikimedia (`.jpg`, `.jpeg`, `.png`, `.webp`).

## 5. Stack constraints

- Web app: zero npm dependencies. Vanilla HTML/CSS/JS, ES modules.
- Local server: `python3 scripts/admin_server.py` (a stdlib subclass of
  `http.server.SimpleHTTPRequestHandler`) is the canonical launcher. It serves
  static files (web/, data/) AND exposes `/api/...` mutation endpoints + an
  `/admin/` curation UI. Binds to `127.0.0.1` only — never `0.0.0.0`. Do not
  fall back to `python3 -m http.server` (no admin endpoints).
- Python scripts: zero pip dependencies. `urllib`, `json`, `hashlib`, `pathlib`,
  `argparse`, `unittest`, `http.server`, `email.parser`, `threading`,
  `importlib.util` from stdlib only.
- All code must run on macOS and Windows.

## 6. Wikimedia API etiquette

- Always send a descriptive `User-Agent` header per
  https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy:
  `celeb-quiz-image/1.0 (+https://github.com/vkehfdl1/celeb-quiz) Python/3.x`
- Sequential requests, ~1 req/sec. Exponential backoff on HTTP 429.
- Filter `pilicense=free` on `prop=pageimages` in the default `--source wiki-free` mode.
- Try `ko.wikipedia.org` first, fall back to `en.wikipedia.org`.

## 7. Atomic commit policy

- Each commit is self-contained and passes its own tests in isolation.
- Conventional Commits prefixes: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`,
  `test:`. Optional scopes: `feat(skill):`, `feat(web):`, `feat(data):`.
- No squash, no force push to `main`.

## 8. Testing

- Python: `python3 -m unittest discover scripts/tests`. No pytest, no fixtures lib.
- Web JS: open `http://localhost:8000/web/tests/test.html` in a browser; assertions
  log pass/fail to the page. No Node test runner.
- Mock all network calls with `unittest.mock.patch('urllib.request.urlopen')`.

## 9. What NOT to do

- Do NOT add npm or pip dependencies.
- Do NOT add a build step (Webpack, Vite, Rollup, Babel, TypeScript).
- Do NOT publish or commercially use `data/` directories fetched with `--source wiki-any`,
  `--source auto`, or `--allow-non-free`.
- Do NOT inline images as base64 into `list.jsonl`.
- Do NOT commit fetched images for any quiz other than `example-historical-figures`.
- Do NOT change `id` of an existing entry without also renaming its image file.
