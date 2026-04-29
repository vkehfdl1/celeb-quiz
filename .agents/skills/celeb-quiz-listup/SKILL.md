---
name: celeb-quiz-listup
description: >
  Build a person/celebrity list for the celeb-quiz app. Use when the user says
  "퀴즈 인물 목록 만들기", "celeb-quiz 인물 추가", "create celebrity quiz list",
  "list up celebrities for quiz", "야구선수 퀴즈 만들어줘", "아이돌 퀴즈 인물 추가",
  or asks to seed a new quiz with people from any category (baseball players,
  K-pop idols, actors, politicians, historical figures, athletes, etc.).
metadata:
  version: "1.0.0"
---

# Celeb Quiz — List-up Skill

You are the list-up agent for the celeb-quiz project. Your job is to interview the user, generate a curated list of people in a chosen category, and write the result to `data/quizzes/<slug>/list.jsonl` following the schema in `references/jsonl-schema.md`.

## When to use this skill

Load this skill whenever the user wants to build or extend a person list for a celeb-quiz. Common trigger phrases:

- "퀴즈 인물 목록 만들기" / "인물 추가해줘"
- "celeb-quiz 인물 추가" / "celeb-quiz listup"
- "야구선수 퀴즈 만들어줘" / "아이돌 퀴즈 인물 추가"
- "create celebrity quiz list" / "list up celebrities for quiz"
- "seed a new quiz with [category]"
- Any request to populate a quiz with people from a named category (athletes, actors, politicians, historical figures, K-pop idols, etc.)

## Output contract

Each person becomes one JSON object on its own line in `data/quizzes/<slug>/list.jsonl`. No enclosing array. UTF-8, `ensure_ascii=False`.

Minimal listup-time line:

```json
{"id": "lee-jung-hoo", "name": "이정후", "category": "야구선수", "disambiguation": "키움 히어로즈 외야수"}
```

Full schema and validation rules: see [`references/jsonl-schema.md`](references/jsonl-schema.md).

## Interview protocol

Follow these steps in order. Do not skip steps.

### Step 1 — Category

Ask the user for the category. Accept free-form Korean or English.

> "어떤 분야의 인물 목록을 만들까요? (예: 야구선수, K-pop 아이돌 4세대, 대한민국 대통령, 조선시대 위인, 헐리우드 배우)"

Check `references/category-examples.md` for starter candidates and expected free-image hit rates. If the category is LOW hit-rate (K-pop idols, contemporary actors), warn the user now:

> "이 카테고리는 자유 라이선스 이미지 확보율이 낮습니다. 사진을 못 찾는 인물이 많을 수 있어요."

### Step 2 — Target count

Ask how many people to include. Default 20, range 5–100.

> "몇 명을 목록에 넣을까요? (기본값: 20명, 최대 100명)"

### Step 3 — Name language

Ask whether `name` values should be Korean or English. Default: Korean if the category is Korean-centric, English otherwise.

> "이름 표기를 한국어로 할까요, 영어로 할까요? (기본값: 카테고리에 맞게 자동 선택)"

### Step 4 — Quiz directory slug

Propose a kebab-case ASCII slug based on the category (e.g. "kbo-stars-2024", "kpop-4th-gen", "joseon-figures"). Ask the user to confirm or change it.

Validation: must match `^[a-z0-9][a-z0-9-]{1,59}$`. Reject and re-ask if invalid.

> "퀴즈 폴더 이름을 'kbo-stars-2024'로 할까요? 다른 이름을 원하시면 말씀해 주세요."

### Step 5 — Batch review

Generate candidates in batches of 10. Present each batch as a numbered table:

```
#  | name       | category | disambiguation
---|------------|----------|---------------------------
1  | 이정후     | 야구선수 | 키움 히어로즈 외야수
2  | 김광현     | 야구선수 | SSG 랜더스 투수
...
```

Ask the user to:
- Mark removals: "1, 3, 7 빼줘"
- Request replacements: "2번을 박병호로 바꿔줘"
- Approve the batch: "다 좋아" / "OK"

Apply edits, then move to the next batch. Do not write to disk until the user approves each batch.

### Step 6 — Write to disk

After all batches are approved, create `data/quizzes/<slug>/` if it doesn't exist, then append each approved entry as one JSON line to `data/quizzes/<slug>/list.jsonl`. Use `ensure_ascii=False`.

If the file already exists, append (do not overwrite). Check for `id` collisions with existing entries; if found, append `-2`, `-3`, etc.

### Step 7 — Confirm

Print a summary:

```
완료! data/quizzes/kbo-stars-2024/list.jsonl 에 23명 추가됨.
샘플 ID: lee-jung-hoo, kim-gwang-hyeon, park-byung-ho
```

Then remind the user of the next step (see **Hand-off** below).

## ID generation rule

The `id` field must be a unique, lowercase ASCII kebab-case slug. Max 60 chars.

**For Korean names**, apply Revised Romanization of Korean (국립국어원 표준):

| Korean name | id |
|-------------|-----|
| 이순신 | `yi-sun-sin` |
| 세종대왕 | `sejong-the-great` |
| 안중근 | `ahn-jung-geun` |
| 이정후 | `lee-jung-hoo` |
| 손흥민 | `son-heung-min` |
| 박찬호 | `park-chan-ho` |
| 김광현 | `kim-gwang-hyeon` |
| 유관순 | `yu-gwan-sun` |

Family-name conventions (use the common romanization for that person):

- 이 → Lee (living people), Yi (historical)
- 박 → Park, 김 → Kim, 최 → Choi, 정 → Jung or Jeong
- 안 → Ahn, 송 → Song, 손 → Son, 임 → Lim, 한 → Han

**For non-Korean names**, lowercase and hyphenate words:

- Taylor Swift → `taylor-swift`
- Lionel Messi → `lionel-messi`
- Timothée Chalamet → `timothee-chalamet` (strip diacritics)

**Collision handling**: if two people share the same romanization, append `-2`, `-3` to the later entry. Document the disambiguation field to help distinguish them.

## Disambiguation field

Set `disambiguation` whenever the name alone is ambiguous. Examples:

- `이정후` → `"키움 히어로즈 외야수"` (there are other 이정후)
- `김구` → `"백범, 대한민국 임시정부 주석"` (very common name)
- `이승만` → `"독립운동가 시기"` or `"대한민국 초대 대통령"` depending on context
- `정약용` → `"조선 후기 실학자, 다산"` (alias hint)

Leave `disambiguation` empty (`""`) or omit it for unambiguous names like "세종대왕" or "Lionel Messi".

## Output file location

```
data/quizzes/<slug>/list.jsonl
```

Relative to the repo root. Create parent directories if missing. Always write with `ensure_ascii=False` so Korean characters remain readable in the file (not escaped as `\uXXXX`).

## Hand-off

After listup finishes, tell the user:

> "다음 단계: `celeb-quiz-image` 스킬을 실행해서 `data/quizzes/<slug>/list.jsonl` 의 인물 사진을 가져오세요. 그 다음 `celeb-quiz-setup` 스킬로 퀴즈 매니페스트를 만들면 됩니다."

## See also

- [`references/jsonl-schema.md`](references/jsonl-schema.md) — full field schema and validation rules
- [`references/category-examples.md`](references/category-examples.md) — starter candidates and hit-rate guidance per category
