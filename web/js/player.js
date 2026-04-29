/**
 * celeb-quiz player display.
 *
 * Public-facing screen. Subscribes to the host's BroadcastChannel and renders
 * photo, countdown, "땡!" overlay, reveal panel, and attribution. No controls.
 *
 * @module player
 */
import { QuizSync, EVENTS } from './sync.js';

const params = new URLSearchParams(location.search);
const quizName = params.get('quiz');
const initialCountdown = parseInt(params.get('countdown') || '7', 10) || 7;

if (!quizName) {
  document.body.innerHTML = '<div class="player"><div class="empty">퀴즈가 지정되지 않았습니다.<div class="hint">index 화면에서 다시 시작해 주세요.</div></div></div>';
  throw new Error('No quiz parameter');
}

const channelName = `celeb-quiz:${quizName}`;
const sync = new QuizSync(channelName);

const dom = {
  waiting: document.getElementById('waiting'),
  stage: document.getElementById('stage'),
  photo: document.getElementById('photo'),
  countdown: document.getElementById('countdown'),
  dang: document.getElementById('dang'),
  reveal: document.getElementById('reveal'),
  revealName: document.getElementById('reveal-name'),
  revealCategory: document.getElementById('reveal-category'),
  attribution: document.getElementById('attribution'),
  fsHint: document.getElementById('fs-hint'),
};

let currentEntry = null;
let lastCountdown = initialCountdown;

function showWaiting() {
  dom.waiting.style.display = '';
  dom.stage.hidden = true;
  dom.countdown.hidden = true;
  dom.dang.hidden = true;
  dom.attribution.hidden = true;
  hideReveal();
}

function showEntry(entry, countdown) {
  currentEntry = entry;
  dom.waiting.style.display = 'none';
  dom.stage.hidden = false;
  dom.dang.hidden = true;
  dom.countdown.hidden = false;
  dom.countdown.classList.remove('warn', 'danger');
  dom.attribution.hidden = false;
  hideReveal();

  if (dom.photo.src !== entry.image_url) {
    dom.photo.classList.add('fade-out');
    setTimeout(() => {
      dom.photo.src = entry.image_url;
      dom.photo.alt = entry.name;
      dom.photo.classList.remove('fade-out');
    }, 60);
  }

  setCountdown(countdown ?? initialCountdown);
  renderAttribution(entry);
}

function setCountdown(n) {
  lastCountdown = n;
  dom.countdown.textContent = String(n);
  dom.countdown.classList.toggle('warn', n > 0 && n <= 3);
  dom.countdown.classList.toggle('danger', n === 0);
}

function showDang() {
  if (!currentEntry) return;
  dom.countdown.hidden = true;
  dom.dang.hidden = false;
}

function showReveal(entry) {
  dom.revealName.textContent = entry.name;
  dom.revealCategory.textContent = entry.category || '';
  dom.reveal.classList.add('shown');
}

function hideReveal() {
  dom.reveal.classList.remove('shown');
}

function renderAttribution(entry) {
  if (!entry.license) {
    dom.attribution.innerHTML = '';
    return;
  }
  const artist = entry.artist ? `${escapeHtml(entry.artist)} · ` : '';
  const lic = entry.license_url
    ? `<a href="${escapeAttr(entry.license_url)}" target="_blank" rel="noopener">${escapeHtml(entry.license)}</a>`
    : escapeHtml(entry.license);
  const src = entry.image_source_url
    ? `<a href="${escapeAttr(entry.image_source_url)}" target="_blank" rel="noopener">Wikimedia Commons</a>`
    : 'Wikimedia Commons';
  dom.attribution.innerHTML = `${artist}${lic} · ${src}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

sync.respondToHeartbeat();

sync.subscribe(EVENTS.START, ({ entry, countdown }) => {
  showEntry(entry, countdown);
});
sync.subscribe(EVENTS.NEXT, ({ entry, countdown }) => {
  showEntry(entry, countdown);
});
sync.subscribe(EVENTS.RESTART, ({ entry, countdown }) => {
  showEntry(entry, countdown);
});
sync.subscribe(EVENTS.TICK, ({ remaining }) => {
  setCountdown(remaining);
});
sync.subscribe(EVENTS.EXPIRED, ({ entry }) => {
  if (!currentEntry) return;
  if (entry && entry.id && entry.id !== currentEntry.id) return;
  showDang();
});
sync.subscribe(EVENTS.REVEAL, ({ entry }) => {
  showReveal(entry || currentEntry);
});
sync.subscribe(EVENTS.CLOSE, () => {
  showWaiting();
});

let fsHidden = false;
function hideFsHint() {
  if (!fsHidden) {
    dom.fsHint.style.display = 'none';
    fsHidden = true;
  }
}
document.addEventListener('fullscreenchange', hideFsHint);
setTimeout(hideFsHint, 8000);

showWaiting();

window.addEventListener('beforeunload', () => sync.close());
