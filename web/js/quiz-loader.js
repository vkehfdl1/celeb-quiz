/**
 * Fetches and parses celeb-quiz data files: the top-level index.json
 * and per-quiz quiz.json + list.jsonl pairs.
 *
 * @module quiz-loader
 */

/**
 * Error thrown when a quiz file cannot be loaded or parsed.
 * `.line` is set when the failure was on a specific JSONL line (1-indexed).
 */
export class QuizLoadError extends Error {
  constructor(message, { line, cause } = {}) {
    super(message);
    this.name = 'QuizLoadError';
    if (typeof line === 'number') this.line = line;
    if (cause) this.cause = cause;
  }
}

/**
 * Fetches `${basePath}/index.json` and returns the parsed object.
 * Returns `{quizzes: []}` on HTTP 404 (a missing index is a valid
 * empty state). Throws `QuizLoadError` on JSON parse failure.
 *
 * @param {string} [basePath='/data/quizzes']
 * @returns {Promise<{quizzes: Array<object>}>}
 */
export async function loadIndex(basePath = '/data/quizzes') {
  const url = `${basePath}/index.json`;
  const res = await fetch(url);
  if (res.status === 404) return { quizzes: [] };
  if (!res.ok) {
    throw new QuizLoadError(`Failed to fetch ${url}: HTTP ${res.status}`);
  }
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new QuizLoadError(`Invalid JSON in ${url}: ${err.message}`, { cause: err });
  }
  if (!data || !Array.isArray(data.quizzes)) {
    return { quizzes: [], ...((data && typeof data === 'object') ? data : {}) };
  }
  return data;
}

/**
 * Fetches a quiz manifest and JSONL entry list, parses both, and filters
 * out entries that have no usable image. The returned `basePath` is the
 * URL prefix callers should use to resolve relative `image_path` fields.
 *
 * Filter rule: an entry is dropped from the returned `entries` array if
 * `fetch_status !== "ok"` OR if `image_path` is missing/empty. The web
 * app should never display non-image entries.
 *
 * @param {string} name - Quiz directory name (slug).
 * @param {string} [basePath='/data/quizzes']
 * @returns {Promise<{manifest: object, entries: Array<object>, basePath: string}>}
 * @throws {QuizLoadError}
 */
export async function loadQuiz(name, basePath = '/data/quizzes') {
  const root = `${basePath}/${name}`;
  const manifestUrl = `${root}/quiz.json`;
  const listUrl = `${root}/list.jsonl`;

  const [manifestRes, listRes] = await Promise.all([fetch(manifestUrl), fetch(listUrl)]);
  if (!manifestRes.ok) {
    throw new QuizLoadError(`Failed to fetch ${manifestUrl}: HTTP ${manifestRes.status}`);
  }
  if (!listRes.ok) {
    throw new QuizLoadError(`Failed to fetch ${listUrl}: HTTP ${listRes.status}`);
  }

  const manifestText = await manifestRes.text();
  let manifest;
  try {
    manifest = JSON.parse(manifestText);
  } catch (err) {
    throw new QuizLoadError(`Invalid JSON in ${manifestUrl}: ${err.message}`, { cause: err });
  }

  const listText = await listRes.text();
  const entries = parseJsonl(listText, listUrl);
  const filtered = entries.filter(
    (e) => e && e.fetch_status === 'ok' && typeof e.image_path === 'string' && e.image_path.length > 0,
  );

  return { manifest, entries: filtered, basePath: root };
}

function parseJsonl(text, sourceUrl) {
  const out = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    if (raw.trim() === '') continue;
    try {
      out.push(JSON.parse(raw));
    } catch (err) {
      throw new QuizLoadError(
        `Invalid JSON on line ${i + 1} of ${sourceUrl}: ${err.message}`,
        { line: i + 1, cause: err },
      );
    }
  }
  return out;
}
