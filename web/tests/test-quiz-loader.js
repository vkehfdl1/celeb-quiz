import { test, assert, assertEqual, assertRejects } from './harness.js';
import { loadIndex, loadQuiz, QuizLoadError } from '../js/quiz-loader.js';

function mockResponse(body, { status = 200 } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() { return typeof body === 'string' ? body : JSON.stringify(body); },
  };
}

function installFetch(routes) {
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (url in routes) return routes[url];
    return mockResponse('not found', { status: 404 });
  };
  return () => { globalThis.fetch = original; };
}

test('loadIndex parses index.json', async () => {
  const restore = installFetch({
    '/data/quizzes/index.json': mockResponse({ quizzes: [{ id: 'a', name: 'A' }] }),
  });
  try {
    const idx = await loadIndex();
    assertEqual(idx.quizzes.length, 1);
    assertEqual(idx.quizzes[0].id, 'a');
  } finally { restore(); }
});

test('loadIndex returns empty quizzes on 404', async () => {
  const restore = installFetch({
    '/data/quizzes/index.json': mockResponse('missing', { status: 404 }),
  });
  try {
    const idx = await loadIndex();
    assertEqual(idx, { quizzes: [] });
  } finally { restore(); }
});

test('loadIndex throws QuizLoadError on invalid JSON', async () => {
  const restore = installFetch({
    '/data/quizzes/index.json': mockResponse('{ this is not json', { status: 200 }),
  });
  try {
    await assertRejects(() => loadIndex(), QuizLoadError);
  } finally { restore(); }
});

test('loadQuiz parses quiz.json + list.jsonl', async () => {
  const jsonl = [
    JSON.stringify({ id: 'a', name: 'Alpha', fetch_status: 'ok', image_path: 'images/a.jpg' }),
    JSON.stringify({ id: 'b', name: 'Beta', fetch_status: 'ok', image_path: 'images/b.jpg' }),
  ].join('\n');
  const restore = installFetch({
    '/data/quizzes/q1/quiz.json': mockResponse({ name: 'q1', count: 2 }),
    '/data/quizzes/q1/list.jsonl': mockResponse(jsonl),
  });
  try {
    const r = await loadQuiz('q1');
    assertEqual(r.manifest.name, 'q1');
    assertEqual(r.entries.length, 2);
    assertEqual(r.entries[0].id, 'a');
    assertEqual(r.basePath, '/data/quizzes/q1');
  } finally { restore(); }
});

test('loadQuiz skips blank lines in JSONL', async () => {
  const jsonl = [
    '',
    JSON.stringify({ id: 'a', fetch_status: 'ok', image_path: 'p1' }),
    '   ',
    JSON.stringify({ id: 'b', fetch_status: 'ok', image_path: 'p2' }),
    '',
  ].join('\n');
  const restore = installFetch({
    '/data/quizzes/q1/quiz.json': mockResponse({}),
    '/data/quizzes/q1/list.jsonl': mockResponse(jsonl),
  });
  try {
    const r = await loadQuiz('q1');
    assertEqual(r.entries.length, 2);
  } finally { restore(); }
});

test('loadQuiz throws QuizLoadError with line number on bad JSON line', async () => {
  const jsonl = [
    JSON.stringify({ id: 'a', fetch_status: 'ok', image_path: 'p1' }),
    'this is not valid json',
    JSON.stringify({ id: 'c', fetch_status: 'ok', image_path: 'p3' }),
  ].join('\n');
  const restore = installFetch({
    '/data/quizzes/q1/quiz.json': mockResponse({}),
    '/data/quizzes/q1/list.jsonl': mockResponse(jsonl),
  });
  try {
    let caught = null;
    try { await loadQuiz('q1'); } catch (e) { caught = e; }
    assert(caught instanceof QuizLoadError, 'did not throw QuizLoadError');
    assertEqual(caught.line, 2, `expected line 2, got ${caught.line}`);
  } finally { restore(); }
});

test('loadQuiz filters out entries with fetch_status != "ok"', async () => {
  const jsonl = [
    JSON.stringify({ id: 'a', fetch_status: 'ok', image_path: 'p1' }),
    JSON.stringify({ id: 'b', fetch_status: 'no_free_image', image_path: 'p2' }),
    JSON.stringify({ id: 'c', fetch_status: 'error', image_path: 'p3' }),
  ].join('\n');
  const restore = installFetch({
    '/data/quizzes/q1/quiz.json': mockResponse({}),
    '/data/quizzes/q1/list.jsonl': mockResponse(jsonl),
  });
  try {
    const r = await loadQuiz('q1');
    assertEqual(r.entries.length, 1);
    assertEqual(r.entries[0].id, 'a');
  } finally { restore(); }
});

test('loadQuiz filters out entries without image_path', async () => {
  const jsonl = [
    JSON.stringify({ id: 'a', fetch_status: 'ok', image_path: 'p1' }),
    JSON.stringify({ id: 'b', fetch_status: 'ok' }),
    JSON.stringify({ id: 'c', fetch_status: 'ok', image_path: '' }),
  ].join('\n');
  const restore = installFetch({
    '/data/quizzes/q1/quiz.json': mockResponse({}),
    '/data/quizzes/q1/list.jsonl': mockResponse(jsonl),
  });
  try {
    const r = await loadQuiz('q1');
    assertEqual(r.entries.length, 1);
    assertEqual(r.entries[0].id, 'a');
  } finally { restore(); }
});
