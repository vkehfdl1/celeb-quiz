# Image License Policy — celeb-quiz

This document is the authoritative license policy for all images used in
celeb-quiz. It can be read independently of the rest of the project.

---

## Allowed license families

Only images under these four families may be saved:

| Family | Examples | Attribution required? |
|--------|----------|----------------------|
| **Public Domain** | PD-old, PD-USGov, PD-self | No |
| **CC0** | Creative Commons Zero | No |
| **CC-BY** | CC BY 2.0, CC BY 4.0 | Yes |
| **CC-BY-SA** | CC BY-SA 3.0, CC BY-SA 4.0 | Yes |

---

## Forbidden categories

The following are **never** acceptable, regardless of how the image is sourced:

| Category | Why forbidden |
|----------|---------------|
| **All rights reserved** | No permission to reproduce or display. |
| **Fair use** | Fair use is a US legal defense, not a license. It does not transfer to other jurisdictions and cannot be relied on for a self-hosted app. |
| **NC (NonCommercial)** | CC BY-NC and CC BY-NC-SA prohibit commercial use. We cannot guarantee the quiz will never be used commercially, so NC images are blocked unconditionally. |
| **ND (NoDerivatives)** | CC BY-ND prohibits creating derivative works. Resizing, cropping, or re-encoding an image for display may constitute a derivative. |

Unknown or missing license metadata is treated as forbidden. If
`LicenseShortName` is absent from Commons extmetadata, the entry is marked
`no_free_image` and no image is saved.

---

## Attribution requirements for CC-BY and CC-BY-SA

When an image is CC-BY or CC-BY-SA, all four of the following fields must be
present in `list.jsonl` and displayed in the web app:

| Field | Description | Display location |
|-------|-------------|-----------------|
| `artist` | Creator name, HTML-stripped | Attribution line |
| `license` | Short name, e.g. "CC BY-SA 4.0" | Attribution line |
| `license_url` | URL to the license deed | Linked from attribution |
| `image_source_url` | Direct URL to the Commons file | Linked from attribution |

The web app shows attribution in **both** the host control window and the player
display window, in an always-visible position (bottom-right corner). This is a
project-level decision and is not negotiable.

Public Domain and CC0 images do not legally require attribution, but the
`artist` field is still populated when available as a courtesy.

---

## Technical enforcement chain

Three layers enforce this policy automatically:

1. **`pilicense=free` API filter** — `fetch.py` passes this parameter to the
   Wikipedia `pageimages` API. Wikipedia's MediaWiki server excludes non-free
   images before returning results.

2. **`LicenseShortName` check** — `fetch.py` reads `LicenseShortName` from
   Wikimedia Commons `extmetadata`. If the field is missing or empty, the entry
   is marked `no_free_image` and no image is downloaded.

3. **`validate.py --strict` exit code** — the setup skill's validator exits
   non-zero if any entry has `fetch_status != "ok"`. This blocks quiz
   publication until all entries are resolved.

---

## Manual override is forbidden

AGENTS.md §3 states: non-free, fair-use, "all rights reserved", or
unknown-license images **must** be skipped. Manually editing `list.jsonl` to
add an `image_path` for a non-free image bypasses all three enforcement layers
and violates this policy.

If a celebrity has no free image on Wikipedia, the correct responses are:

- Set `fetch_status: "no_free_image"` and leave `image_path` absent.
- Add a `disambiguation` field and retry (a different Wikipedia page may have a
  free image).
- Remove the entry from the quiz entirely.

**Never** source images from Google Images, Bing, Naver, or any non-Wikimedia
source through the `celeb-quiz-image` skill.
