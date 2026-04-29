import { test, skip, assert, assertEqual } from './harness.js';
import { QuizSync, EVENTS } from '../js/sync.js';

const HAS_BC = typeof BroadcastChannel !== 'undefined';

function uniqueChannel(label) {
  return `celeb-quiz-test-${label}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function waitFor(predicate, { timeoutMs = 1000, intervalMs = 10 } = {}) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const id = setInterval(() => {
      if (predicate()) { clearInterval(id); resolve(); }
      else if (Date.now() - start > timeoutMs) {
        clearInterval(id);
        reject(new Error(`waitFor timed out after ${timeoutMs}ms`));
      }
    }, intervalMs);
  });
}

test('EVENTS constants are exported and are non-empty strings', () => {
  const required = ['START', 'NEXT', 'REVEAL', 'TICK', 'EXPIRED', 'RESTART', 'CLOSE', 'PING', 'PONG'];
  for (const k of required) {
    assert(typeof EVENTS[k] === 'string', `EVENTS.${k} not a string`);
    assert(EVENTS[k].length > 0, `EVENTS.${k} is empty`);
  }
});

if (!HAS_BC) {
  skip('QuizSync.publish/subscribe round-trips an event', 'BroadcastChannel unavailable');
  skip('subscribe returns an unsubscribe function that stops further deliveries', 'BroadcastChannel unavailable');
  skip('subscribeAll receives messages of any event type', 'BroadcastChannel unavailable');
  skip('Heartbeat: PING/PONG round-trip when both endpoints active', 'BroadcastChannel unavailable');
  skip('Heartbeat: onTimeout fires when peer is silent', 'BroadcastChannel unavailable');
} else {
  test('QuizSync.publish/subscribe round-trips an event', async () => {
    const ch = uniqueChannel('roundtrip');
    const a = new QuizSync(ch);
    const b = new QuizSync(ch);
    let received = null;
    b.subscribe(EVENTS.START, (payload) => { received = payload; });
    a.publish(EVENTS.START, { quiz: 'q1' });
    await waitFor(() => received !== null);
    assertEqual(received, { quiz: 'q1' });
    a.close(); b.close();
  });

  test('subscribe returns an unsubscribe function that stops further deliveries', async () => {
    const ch = uniqueChannel('unsub');
    const a = new QuizSync(ch);
    const b = new QuizSync(ch);
    let count = 0;
    const unsub = b.subscribe(EVENTS.NEXT, () => { count++; });
    a.publish(EVENTS.NEXT, { i: 1 });
    await waitFor(() => count === 1);
    unsub();
    a.publish(EVENTS.NEXT, { i: 2 });
    await new Promise((r) => setTimeout(r, 80));
    assertEqual(count, 1, 'handler ran after unsubscribe');
    a.close(); b.close();
  });

  test('subscribeAll receives messages of any event type', async () => {
    const ch = uniqueChannel('all');
    const a = new QuizSync(ch);
    const b = new QuizSync(ch);
    const seen = [];
    b.subscribeAll((_p, m) => { seen.push(m.event); });
    a.publish(EVENTS.START);
    a.publish(EVENTS.REVEAL);
    a.publish(EVENTS.EXPIRED);
    await waitFor(() => seen.length >= 3);
    assert(seen.includes(EVENTS.START), 'missing START');
    assert(seen.includes(EVENTS.REVEAL), 'missing REVEAL');
    assert(seen.includes(EVENTS.EXPIRED), 'missing EXPIRED');
    a.close(); b.close();
  });

  test('Heartbeat: PING/PONG round-trip when both endpoints active', async () => {
    const ch = uniqueChannel('hb-ok');
    const host = new QuizSync(ch);
    const player = new QuizSync(ch);
    player.respondToHeartbeat();
    let timedOut = false;
    const stop = host.enableHeartbeat({
      intervalMs: 50,
      timeoutMs: 500,
      onTimeout: () => { timedOut = true; },
    });
    await new Promise((r) => setTimeout(r, 250));
    assertEqual(timedOut, false, 'timeout fired despite responsive peer');
    stop();
    host.close(); player.close();
  });

  test('Heartbeat: onTimeout fires when peer is silent', async () => {
    const ch = uniqueChannel('hb-silent');
    const host = new QuizSync(ch);
    let timedOut = false;
    const stop = host.enableHeartbeat({
      intervalMs: 30,
      timeoutMs: 100,
      onTimeout: () => { timedOut = true; },
    });
    await waitFor(() => timedOut === true, { timeoutMs: 1000, intervalMs: 20 });
    stop();
    host.close();
  });
}
