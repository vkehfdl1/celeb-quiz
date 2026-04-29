# Category Examples — celeb-quiz-listup

Use this reference to bootstrap candidate lists and set user expectations about image availability before starting a quiz.

---

## Free-image hit rate guide

| Rating | Meaning | Typical categories |
|--------|---------|-------------------|
| **HIGH** | Most people have a free-licensed photo on Wikimedia | Historical figures, classical composers, politicians with long careers |
| **MEDIUM** | Roughly half will have a usable image | Athletes, scientists, authors, modern politicians |
| **LOW** | Many will return `fetch_status: "no_free_image"` | K-pop idols, contemporary actors, current pop musicians |

When the user picks a LOW category, warn them before generating candidates:

> "이 카테고리는 자유 라이선스 이미지 확보율이 낮습니다. 사진을 못 찾는 인물이 많을 수 있어요. 계속 진행할까요?"

---

## 1. 야구선수 (KBO 현역 스타)

**Expected hit rate: MEDIUM**

| name | id | disambiguation |
|------|----|----------------|
| 이정후 | `lee-jung-hoo` | 키움 히어로즈 외야수 |
| 김광현 | `kim-gwang-hyeon` | SSG 랜더스 투수 |
| 박병호 | `park-byung-ho` | KT 위즈 1루수 |
| 김혜성 | `kim-hye-seong` | 키움 히어로즈 내야수 |
| 양현종 | `yang-hyeon-jong` | KIA 타이거즈 투수 |

Note: Active KBO players often have Korean Wikipedia articles with free images, but coverage is inconsistent. Retired legends (박찬호, 이승엽) tend to have better image availability.

---

## 2. K-pop 아이돌 4세대

**Expected hit rate: LOW**

| name | id | disambiguation |
|------|----|----------------|
| 김채원 | `kim-chae-won-lesserafim` | 르세라핌 멤버 |
| 민지 | `minji-newjeans` | NewJeans 멤버 |
| 안유진 | `ahn-yu-jin` | IVE 멤버 |
| 카리나 | `karina-aespa` | aespa 멤버 |
| 예지 | `yeji-itzy` | ITZY 멤버 |

Note: Most 4th-gen idols do not have free-licensed photos on Wikimedia Commons. Expect `fetch_status: "no_free_image"` for the majority. Warn the user strongly before proceeding.

---

## 3. 대한민국 대통령

**Expected hit rate: HIGH**

| name | id | disambiguation |
|------|----|----------------|
| 김대중 | `kim-dae-jung` | 제15대 대통령 |
| 노무현 | `roh-moo-hyun` | 제16대 대통령 |
| 이명박 | `lee-myung-bak` | 제17대 대통령 |
| 박근혜 | `park-geun-hye` | 제18대 대통령 |
| 문재인 | `moon-jae-in` | 제19대 대통령 |

Note: All former presidents have official portrait photos on Wikimedia Commons under free licenses. Hit rate is very high.

---

## 4. 조선시대 위인

**Expected hit rate: HIGH**

| name | id | disambiguation |
|------|----|----------------|
| 세종대왕 | `sejong-the-great` | 조선 제4대 왕, 한글 창제 |
| 이순신 | `yi-sun-sin` | 조선 중기 무신, 임진왜란 |
| 정약용 | `jeong-yak-yong` | 조선 후기 실학자, 다산 |
| 황희 | `hwang-hui` | 조선 세종 시대 재상 |
| 신사임당 | `sin-saimdang` | 조선 중기 예술가, 율곡 이이의 어머니 |

Note: Historical figures from the Joseon era are well-represented on Wikimedia with public domain paintings and portraits. Expect high hit rates.

---

## 5. 근현대 독립운동가

**Expected hit rate: HIGH**

| name | id | disambiguation |
|------|----|----------------|
| 안중근 | `ahn-jung-geun` | 독립운동가, 이토 히로부미 저격 |
| 유관순 | `yu-gwan-sun` | 3.1운동 독립운동가 |
| 김구 | `kim-gu` | 백범, 대한민국 임시정부 주석 |
| 윤봉길 | `yun-bong-gil` | 독립운동가, 홍커우 공원 의거 |
| 이승만 | `yi-seung-man` | 독립운동가 시기 (대한민국 초대 대통령과 구분) |

Note: Early 20th-century independence activists have public domain photographs. Hit rate is high. For 이승만, set `disambiguation` carefully since he appears in multiple historical contexts.

---

## 6. 헐리우드 배우 (현역)

**Expected hit rate: LOW**

| name | id | disambiguation |
|------|----|----------------|
| Tom Cruise | `tom-cruise` | 미국 배우, Mission Impossible 시리즈 |
| Margot Robbie | `margot-robbie` | 호주 배우, Barbie (2023) |
| Cillian Murphy | `cillian-murphy` | 아일랜드 배우, Oppenheimer (2023) |
| Zendaya | `zendaya` | 미국 배우·가수, Dune 시리즈 |
| Timothée Chalamet | `timothee-chalamet` | 미국 배우, Dune 시리즈 |

Note: Contemporary Hollywood actors rarely have free-licensed photos on Wikimedia. Press/promotional images are typically copyrighted. Expect LOW hit rates. Older classic actors (Audrey Hepburn, Humphrey Bogart) have better coverage.

---

## 7. 세계 축구선수 (현역 톱티어)

**Expected hit rate: MEDIUM**

| name | id | disambiguation |
|------|----|----------------|
| Lionel Messi | `lionel-messi` | 아르헨티나, Inter Miami |
| Cristiano Ronaldo | `cristiano-ronaldo` | 포르투갈, Al Nassr |
| Erling Haaland | `erling-haaland` | 노르웨이, Manchester City |
| Kylian Mbappé | `kylian-mbappe` | 프랑스, Real Madrid |
| Son Heung-min | `son-heung-min` | 대한민국, Tottenham Hotspur |

Note: Top footballers often have free-licensed photos from official press events or fan uploads. Hit rate is medium. Strip diacritics from IDs (Mbappé → `mbappe`).

---

## 8. 클래식 작곡가

**Expected hit rate: HIGH**

| name | id | disambiguation |
|------|----|----------------|
| Ludwig van Beethoven | `ludwig-van-beethoven` | 독일 작곡가, 교향곡 9번 |
| Johann Sebastian Bach | `johann-sebastian-bach` | 독일 작곡가, 바로크 시대 |
| Wolfgang Amadeus Mozart | `wolfgang-amadeus-mozart` | 오스트리아 작곡가 |
| Pyotr Ilyich Tchaikovsky | `pyotr-ilyich-tchaikovsky` | 러시아 작곡가, 백조의 호수 |
| Frédéric Chopin | `frederic-chopin` | 폴란드 작곡가, 피아노 소품 |

Note: Classical composers who died before 1928 have public domain portraits and engravings on Wikimedia. Hit rate is very high. Strip diacritics from IDs (Frédéric → `frederic`).

---

## Choosing a slug

When proposing a quiz directory slug, combine a short category keyword with a year or qualifier if relevant:

| Category | Suggested slug |
|----------|---------------|
| KBO 현역 스타 | `kbo-stars-2024` |
| K-pop 4세대 아이돌 | `kpop-4th-gen` |
| 대한민국 대통령 | `korean-presidents` |
| 조선시대 위인 | `joseon-figures` |
| 근현대 독립운동가 | `korean-independence-activists` |
| 헐리우드 배우 | `hollywood-actors` |
| 세계 축구선수 | `world-football-stars` |
| 클래식 작곡가 | `classical-composers` |
