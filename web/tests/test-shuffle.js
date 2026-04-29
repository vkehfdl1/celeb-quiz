import { test, assert, assertEqual } from './harness.js';
import { shuffle, seededRng } from '../js/shuffle.js';

test('shuffle returns a new array (does not mutate input)', () => {
  const input = [1, 2, 3, 4, 5];
  const snapshot = input.slice();
  const out = shuffle(input, seededRng(42));
  assert(out !== input, 'returned the same array reference');
  assertEqual(input, snapshot, 'input was mutated');
});

test('shuffle preserves length and multiset', () => {
  const input = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];
  const out = shuffle(input, seededRng(7));
  assertEqual(out.length, input.length, 'length differs');
  const sortedIn = input.slice().sort();
  const sortedOut = out.slice().sort();
  assertEqual(sortedOut, sortedIn, 'multiset differs');
});

test('seededRng with same seed produces same sequence', () => {
  const a = seededRng(123);
  const b = seededRng(123);
  for (let i = 0; i < 16; i++) {
    assertEqual(a(), b(), `divergence at index ${i}`);
  }
});

test('shuffle with seededRng is deterministic', () => {
  const input = [10, 20, 30, 40, 50, 60, 70, 80];
  const out1 = shuffle(input, seededRng(99));
  const out2 = shuffle(input, seededRng(99));
  assertEqual(out1, out2, 'two seeded shuffles diverged');
});

test('shuffle of empty array returns empty array', () => {
  const out = shuffle([], seededRng(1));
  assertEqual(out, []);
});

test('shuffle of single element returns single element', () => {
  const out = shuffle(['only'], seededRng(1));
  assertEqual(out, ['only']);
});
