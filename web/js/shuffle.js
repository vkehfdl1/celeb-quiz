/**
 * Pure Fisher-Yates shuffle with injectable RNG, plus a tiny seedable
 * mulberry32 PRNG for deterministic testing.
 *
 * @module shuffle
 */

/**
 * Returns a NEW array containing the elements of `array` in a uniformly
 * random order. Does not mutate the input.
 *
 * @template T
 * @param {ReadonlyArray<T>} array - Source array (not mutated).
 * @param {() => number} [rng=Math.random] - RNG returning floats in [0, 1).
 * @returns {T[]} A freshly allocated, shuffled copy.
 */
export function shuffle(array, rng = Math.random) {
  const out = array.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
  return out;
}

/**
 * Returns a deterministic RNG seeded with `seed`. Implements mulberry32,
 * which is small, fast, and statistically adequate for shuffling tests.
 *
 * @param {number} seed - 32-bit integer seed.
 * @returns {() => number} Function returning floats in [0, 1).
 */
export function seededRng(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
