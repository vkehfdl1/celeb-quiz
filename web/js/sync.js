/**
 * Cross-tab event bus for the celeb-quiz host/player split.
 *
 * Primary transport: BroadcastChannel. Fallback: localStorage 'storage'
 * events when BroadcastChannel is unavailable (older Safari, some
 * embedded webviews). The fallback writes a unique key each publish so
 * every write triggers a 'storage' event in other tabs of the same origin.
 *
 * @module sync
 */

/**
 * Event vocabulary shared by host and player.
 * @enum {string}
 */
export const EVENTS = Object.freeze({
  START: 'start',
  NEXT: 'next',
  REVEAL: 'reveal',
  TICK: 'tick',
  EXPIRED: 'expired',
  RESTART: 'restart',
  CLOSE: 'close',
  PING: 'ping',
  PONG: 'pong',
});

/**
 * Thin wrapper around BroadcastChannel (with localStorage fallback) that
 * exposes a small publish/subscribe API plus an opt-in heartbeat.
 */
export class QuizSync {
  /**
   * @param {string} [channelName='celeb-quiz']
   */
  constructor(channelName = 'celeb-quiz') {
    this.channelName = channelName;
    this._handlers = new Map();
    this._allHandlers = new Set();
    this._closed = false;
    this._heartbeatTimer = null;
    this._heartbeatWatchdog = null;
    this._lastPongAt = 0;

    if (typeof BroadcastChannel !== 'undefined') {
      this._mode = 'bc';
      this._channel = new BroadcastChannel(channelName);
      this._channel.onmessage = (ev) => this._dispatch(ev.data);
    } else {
      this._mode = 'ls';
      this._storageKey = `__sync__:${channelName}`;
      this._onStorage = (ev) => {
        if (ev.key !== this._storageKey || !ev.newValue) return;
        try {
          this._dispatch(JSON.parse(ev.newValue));
        } catch { /* swallow malformed messages */ }
      };
      if (typeof window !== 'undefined' && window.addEventListener) {
        window.addEventListener('storage', this._onStorage);
      }
    }
  }

  /**
   * Broadcast an event to all other tabs on this channel.
   * @param {string} event
   * @param {object} [payload={}]
   */
  publish(event, payload = {}) {
    if (this._closed) return;
    const msg = { event, payload, ts: Date.now() };
    if (this._mode === 'bc') {
      this._channel.postMessage(msg);
    } else if (typeof localStorage !== 'undefined') {
      const envelope = { ...msg, _nonce: `${msg.ts}-${Math.random()}` };
      localStorage.setItem(this._storageKey, JSON.stringify(envelope));
    }
  }

  /**
   * Subscribe to a single event type.
   * @param {string} event
   * @param {(payload: object, fullMessage: object) => void} handler
   * @returns {() => void} Unsubscribe function.
   */
  subscribe(event, handler) {
    let set = this._handlers.get(event);
    if (!set) {
      set = new Set();
      this._handlers.set(event, set);
    }
    set.add(handler);
    return () => {
      const s = this._handlers.get(event);
      if (s) s.delete(handler);
    };
  }

  /**
   * Subscribe to every message regardless of event type.
   * @param {(payload: object, fullMessage: object) => void} handler
   * @returns {() => void} Unsubscribe function.
   */
  subscribeAll(handler) {
    this._allHandlers.add(handler);
    return () => this._allHandlers.delete(handler);
  }

  /**
   * Host-side: start broadcasting PING every `intervalMs` and call
   * `onTimeout` if no PONG arrives within `timeoutMs`. Returns a stop
   * function that clears all timers.
   * @param {{intervalMs?: number, timeoutMs?: number, onTimeout?: () => void}} [opts]
   * @returns {() => void}
   */
  enableHeartbeat({ intervalMs = 1000, timeoutMs = 3000, onTimeout } = {}) {
    this.stopHeartbeat();
    this._lastPongAt = Date.now();
    const unsubPong = this.subscribe(EVENTS.PONG, () => {
      this._lastPongAt = Date.now();
    });
    this._heartbeatTimer = setInterval(() => this.publish(EVENTS.PING), intervalMs);
    this._heartbeatWatchdog = setInterval(() => {
      if (Date.now() - this._lastPongAt > timeoutMs && typeof onTimeout === 'function') {
        onTimeout();
      }
    }, Math.max(50, Math.floor(intervalMs / 2)));
    return () => {
      unsubPong();
      this.stopHeartbeat();
    };
  }

  /**
   * Player-side: auto-respond to incoming PINGs with PONG.
   * @returns {() => void} Unsubscribe.
   */
  respondToHeartbeat() {
    return this.subscribe(EVENTS.PING, () => this.publish(EVENTS.PONG));
  }

  /** Stop heartbeat timers without closing the channel. */
  stopHeartbeat() {
    if (this._heartbeatTimer) {
      clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
    if (this._heartbeatWatchdog) {
      clearInterval(this._heartbeatWatchdog);
      this._heartbeatWatchdog = null;
    }
  }

  /** Close the channel and tear down listeners. Idempotent. */
  close() {
    if (this._closed) return;
    this._closed = true;
    this.stopHeartbeat();
    if (this._mode === 'bc' && this._channel) {
      this._channel.close();
      this._channel = null;
    } else if (this._mode === 'ls' && typeof window !== 'undefined' && window.removeEventListener) {
      window.removeEventListener('storage', this._onStorage);
    }
    this._handlers.clear();
    this._allHandlers.clear();
  }

  _dispatch(msg) {
    if (!msg || typeof msg !== 'object') return;
    const { event, payload } = msg;
    const set = this._handlers.get(event);
    if (set) {
      for (const h of set) {
        try { h(payload, msg); } catch { /* isolate handler errors */ }
      }
    }
    for (const h of this._allHandlers) {
      try { h(payload, msg); } catch { /* isolate handler errors */ }
    }
  }
}
