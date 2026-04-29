# Wikimedia API Reference — celeb-quiz-image

This document describes the exact API contract used by `scripts/fetch.py`.
Agents debugging or extending the fetcher should treat this as ground truth.

## User-Agent policy

Every request must include a descriptive `User-Agent` header per the
[Wikimedia User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy).
Requests without a proper User-Agent are blocked or throttled.

Default value (set in `fetch.py`):

```
celeb-quiz-image/1.0 (+https://github.com/vkehfdl1/celeb-quiz) Python/3.x
```

Format: `<tool-name>/<version> (<contact-url>) <runtime>`. The contact URL
must point to a page where Wikimedia staff can reach the operator.

---

## Endpoint 1: REST search

Finds candidate Wikipedia pages for a person's name.

```
GET https://{lang}.wikipedia.org/w/rest.php/v1/search/page?q={query}&limit=5
```

- `lang` — `ko` (tried first) or `en` (fallback).
- `q` — the entry's `name` plus optional `disambiguation`, space-joined.
- `limit` — always 5; the script picks the best title match.

**Response shape (relevant paths):**

```json
{
  "pages": [
    {
      "id": 12345,
      "title": "이정후",
      "description": "대한민국의 야구 선수"
    }
  ]
}
```

The script reads `pages[].title` and `pages[].description`. It picks the first
hit whose normalized title contains (or is contained by) the normalized query
name. If no hit matches on `ko`, it falls back to `en` and takes `pages[0]`.

---

## Endpoint 2: pageimages

Fetches the representative image for a Wikipedia page, restricted to free
licenses.

```
GET https://{lang}.wikipedia.org/w/api.php
  ?action=query
  &prop=pageimages
  &titles={title}
  &piprop=thumbnail|original|name
  &pithumbsize=800
  &pilicense=free
  &format=json
```

**`pilicense=free` semantic:** Wikipedia's MediaWiki API filters to images
tagged as freely licensed (CC or Public Domain) at the server side. This is the
first enforcement layer; Commons extmetadata is the second.

**Response shape (relevant paths):**

```json
{
  "query": {
    "pages": {
      "-1": {
        "pageid": -1,
        "title": "이정후",
        "thumbnail": {
          "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/.../800px-....jpg",
          "width": 800,
          "height": 1170
        },
        "original": {
          "source": "https://upload.wikimedia.org/wikipedia/commons/....jpg",
          "width": 1951,
          "height": 2853
        },
        "imagename": "이정후.jpg"
      }
    }
  }
}
```

The script reads:

- `original.source` — full-resolution download URL.
- `original.width` / `original.height` — used for the 400 px minimum check.
- `imagename` — Commons filename, passed to Endpoint 3.

If `original` is absent, the entry is marked `no_free_image`.

---

## Endpoint 3: Commons license metadata

Resolves attribution fields for a Commons file.

```
GET https://commons.wikimedia.org/w/api.php
  ?action=query
  &prop=imageinfo
  &titles=File:{filename}
  &iiprop=extmetadata
  &format=json
```

**Response shape (relevant paths):**

```json
{
  "query": {
    "pages": {
      "12345": {
        "imageinfo": [
          {
            "extmetadata": {
              "LicenseShortName": { "value": "CC BY-SA 4.0" },
              "LicenseUrl":       { "value": "https://creativecommons.org/licenses/by-sa/4.0/" },
              "Artist":           { "value": "<span>Jeon Han</span>" },
              "Credit":           { "value": "via Wikimedia Commons" }
            }
          }
        ]
      }
    }
  }
}
```

Fields the script reads from `extmetadata`:

| Field | Used as | Notes |
|-------|---------|-------|
| `LicenseShortName` | `license` (plain text) | HTML-stripped. Missing = skip entry. |
| `LicenseUrl` | `license_url` | Stored as-is. |
| `Artist` | `artist` (plain text) + `attribution_html` (raw) | `artist` has HTML stripped; `attribution_html` keeps the raw HTML for the web app to render. |
| `Credit` | appended to `attribution_html` | Optional. |

If `LicenseShortName` is missing or empty, the entry is marked `no_free_image`
because attribution cannot be displayed.

---

## Rate limits and retry

- **Pacing:** 1 request per second minimum, enforced by a module-level
  `_last_call_at` timestamp.
- **Retry:** HTTP 429 and 503 trigger exponential backoff: 1 s, 2 s, 4 s, 8 s,
  16 s (up to 5 attempts total). Any other HTTP error raises immediately.
- **After 5 failures:** the entry is marked `error`.

---

## Korean specifics

`ko.wikipedia.org` exposes the same REST and action API surfaces as
`en.wikipedia.org`. The script always tries `ko` first because Korean
celebrities are more reliably described on the Korean edition. The `en` fallback
catches international figures or entries where the Korean page lacks a free
image.

---

## Worked example: 이정후

**Step 1 — search (ko):**

```
GET https://ko.wikipedia.org/w/rest.php/v1/search/page?q=%EC%9D%B4%EC%A0%95%ED%9B%84&limit=5
```

Returns `pages[0].title = "이정후"`.

**Step 2 — pageimages (ko):**

```
GET https://ko.wikipedia.org/w/api.php?action=query&prop=pageimages
    &titles=%EC%9D%B4%EC%A0%95%ED%9B%84&piprop=thumbnail|original|name
    &pithumbsize=800&pilicense=free&format=json
```

Returns `original.width=1951`, `original.height=2853`,
`imagename="이정후.jpg"`.

**Step 3 — Commons license:**

```
GET https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo
    &titles=File:%EC%9D%B4%EC%A0%95%ED%9B%84.jpg&iiprop=extmetadata&format=json
```

Returns `LicenseShortName="CC BY-SA 4.0"`,
`LicenseUrl="https://creativecommons.org/licenses/by-sa/4.0/"`,
`Artist="<span>Jeon Han</span>"`.

**Result written to list.jsonl:**

```json
{
  "fetch_status": "ok",
  "license": "CC BY-SA 4.0",
  "license_short": "cc-by-sa-4.0",
  "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
  "artist": "Jeon Han",
  "image_width": 1951,
  "image_height": 2853,
  "wikipedia_lang": "ko"
}
```
