# JSONL Schema — celeb-quiz list.jsonl

This document defines every field in `data/quizzes/<slug>/list.jsonl`.

---

## Fields set at listup time

These are the only fields the `celeb-quiz-listup` skill writes. Do not invent or pre-fill image fields.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | **yes** | Kebab-case ASCII slug, unique within the file. See ID generation rule in SKILL.md. |
| `name` | string | **yes** | Display name. Korean is fine. |
| `category` | string | **yes** | Group label, e.g. `"야구선수"`, `"K-pop 아이돌"`. |
| `name_aliases` | string[] | no | Alternative names or spellings. Useful for disambiguation or search. |
| `disambiguation` | string | no | Short clarifying phrase when the name alone is ambiguous. |

---

## Fields populated later by celeb-quiz-image

The listup skill must NOT set these. They are written by the image-fetch skill after it queries Wikimedia Commons.

| Field | Description |
|-------|-------------|
| `image_path` | Relative path to the saved image file, e.g. `images/lee-jung-hoo.jpg` |
| `image_source_url` | Original Wikimedia Commons file URL |
| `image_width` | Pixel width of the saved image |
| `image_height` | Pixel height of the saved image |
| `license` | Full license name, e.g. `"CC BY-SA 4.0"` |
| `license_short` | Short label, e.g. `"CC-BY-SA"` |
| `license_url` | URL to the license deed |
| `artist` | Attribution string from Wikimedia `Artist` metadata |
| `attribution_html` | Ready-to-render HTML attribution line for the player UI |
| `wikipedia_title` | Wikipedia page title used to find the image |
| `wikipedia_url` | Full URL to the Wikipedia article |
| `wikipedia_lang` | Language code of the Wikipedia used, e.g. `"ko"` or `"en"` |
| `fetched_at` | ISO 8601 timestamp of when the image was fetched |
| `fetch_status` | `"ok"`, `"no_free_image"`, `"not_found"`, or `"error"` |

---

## Example lines

### Minimal — listup time only (required fields)

```json
{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수"}
```

### With optional listup fields

```json
{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수", "disambiguation": "키움 히어로즈 외야수", "name_aliases": ["Lee Jung-hoo"]}
```

### Fully populated — after image fetch

```json
{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수", "disambiguation": "키움 히어로즈 외야수", "name_aliases": ["Lee Jung-hoo"], "image_path": "images/lee-jung-hoo.jpg", "image_source_url": "https://upload.wikimedia.org/wikipedia/commons/x/xx/Lee_Jung-hoo.jpg", "image_width": 800, "image_height": 1000, "license": "CC BY-SA 4.0", "license_short": "CC-BY-SA", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "artist": "Example Photographer", "attribution_html": "<span>이정후 by Example Photographer, <a href=\"https://creativecommons.org/licenses/by-sa/4.0/\">CC BY-SA 4.0</a></span>", "wikipedia_title": "이정후", "wikipedia_url": "https://ko.wikipedia.org/wiki/이정후", "wikipedia_lang": "ko", "fetched_at": "2024-11-01T12:00:00Z", "fetch_status": "ok"}
```

---

## Validation rules

- **Format**: JSON Lines. One JSON object per line. No enclosing `[` `]` array. No trailing commas.
- **Encoding**: UTF-8. Always write with `ensure_ascii=False` so Korean text stays readable (not `\uXXXX` escaped).
- **Blank lines**: allowed and skipped by validators.
- **`id` regex**: `^[a-z0-9][a-z0-9-]{0,59}$`
  - Starts with a lowercase letter or digit.
  - Contains only lowercase ASCII letters, digits, and hyphens.
  - Max 60 characters total.
  - Must be unique within the file.
- **`name`**: non-empty string. Korean characters are fine.
- **`category`**: non-empty string. Should be consistent across entries in the same file.
- **`name_aliases`**: if present, must be a JSON array of strings (not a bare string).
- **Image fields**: if `fetch_status` is `"ok"`, then `image_path`, `license`, `artist`, and `attribution_html` must all be present and non-empty.
