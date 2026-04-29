/**
 * Tiny zero-dep test harness for browser-based unit tests.
 *
 * @module harness
 */

const queue = [];

/**
 * Register a (possibly async) test.
 * @param {string} name
 * @param {() => (void|Promise<void>)} fn
 */
export function test(name, fn) {
  queue.push({ name, fn, status: 'pending', error: null });
}

/**
 * Mark a test as skipped without running it (e.g. unsupported browser API).
 * @param {string} name
 * @param {string} [reason]
 */
export function skip(name, reason = '') {
  queue.push({ name, fn: null, status: 'skip', skipReason: reason, error: null });
}

/**
 * Throws if condition is falsy.
 * @param {*} cond
 * @param {string} [message]
 */
export function assert(cond, message = 'assertion failed') {
  if (!cond) throw new Error(message);
}

/**
 * Deep-equality assertion for primitives, arrays, and plain objects.
 * @param {*} actual
 * @param {*} expected
 * @param {string} [message]
 */
export function assertEqual(actual, expected, message = 'values not equal') {
  if (!deepEqual(actual, expected)) {
    const a = safeStringify(actual);
    const e = safeStringify(expected);
    throw new Error(`${message}\n  actual:   ${a}\n  expected: ${e}`);
  }
}

/**
 * Run `fn` synchronously and assert it throws. Optionally check class.
 * @param {() => *} fn
 * @param {Function} [ErrorClass]
 * @param {string} [message]
 */
export function assertThrows(fn, ErrorClass, message = 'expected fn to throw') {
  let threw = false;
  let err = null;
  try {
    fn();
  } catch (e) {
    threw = true;
    err = e;
  }
  if (!threw) throw new Error(message);
  if (ErrorClass && !(err instanceof ErrorClass)) {
    throw new Error(`${message}: expected instance of ${ErrorClass.name}, got ${err && err.constructor && err.constructor.name}`);
  }
}

/**
 * Async version of assertThrows.
 * @param {() => Promise<*>} fn
 * @param {Function} [ErrorClass]
 * @param {string} [message]
 */
export async function assertRejects(fn, ErrorClass, message = 'expected promise to reject') {
  let threw = false;
  let err = null;
  try {
    await fn();
  } catch (e) {
    threw = true;
    err = e;
  }
  if (!threw) throw new Error(message);
  if (ErrorClass && !(err instanceof ErrorClass)) {
    throw new Error(`${message}: expected instance of ${ErrorClass.name}, got ${err && err.constructor && err.constructor.name}`);
  }
}

/** Run all queued tests sequentially and render summary. */
export async function runAll() {
  const results = typeof document !== 'undefined' ? document.getElementById('results') : null;
  let pass = 0;
  let fail = 0;
  let skipped = 0;

  for (const t of queue) {
    if (t.status === 'skip') {
      render(results, t.name, 'skip', t.skipReason);
      skipped++;
      continue;
    }
    try {
      await t.fn();
      t.status = 'pass';
      pass++;
      render(results, t.name, 'pass');
    } catch (err) {
      t.status = 'fail';
      t.error = err;
      fail++;
      render(results, t.name, 'fail', (err && err.stack) || String(err));
      if (typeof console !== 'undefined') console.error(`[FAIL] ${t.name}`, err);
    }
  }

  const summary = typeof document !== 'undefined' ? document.getElementById('summary') : null;
  const total = pass + fail + skipped;
  const text = `${pass}/${total} passed · ${fail} failed · ${skipped} skipped`;
  if (summary) {
    summary.textContent = text;
    summary.className = fail === 0 ? 'all-green' : 'has-fail';
  }
  if (typeof console !== 'undefined') {
    (fail === 0 ? console.log : console.error)(`[SUMMARY] ${text}`);
  }
  return { pass, fail, skipped, total };
}

function render(container, name, status, detail) {
  if (typeof console !== 'undefined') {
    const tag = status.toUpperCase();
    console.log(`[${tag}] ${name}${detail ? ' — ' + String(detail).split('\n')[0] : ''}`);
  }
  if (!container) return;
  const div = document.createElement('div');
  div.className = `test ${status}`;
  const prefix = status === 'pass' ? '✓' : status === 'fail' ? '✗' : '○';
  div.textContent = `${prefix} ${name}${detail ? '\n  ' + detail : ''}`;
  container.appendChild(div);
}

function deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (!deepEqual(a[i], b[i])) return false;
    return true;
  }
  const ak = Object.keys(a);
  const bk = Object.keys(b);
  if (ak.length !== bk.length) return false;
  for (const k of ak) if (!deepEqual(a[k], b[k])) return false;
  return true;
}

function safeStringify(v) {
  try { return JSON.stringify(v); } catch { return String(v); }
}
