import { loadQuiz } from './quiz-loader.js';
import { shuffle } from './shuffle.js';
import { QuizSync, EVENTS } from './sync.js';

const QUIZ_BASE = '/data/quizzes';

const params = new URLSearchParams(location.search);
const quizName = params.get('quiz');
const initialCountdown = clampCountdown(parseInt(params.get('countdown') || '7', 10));

if (!quizName) {
  document.body.innerHTML = '<div class="container"><div class="empty-state">퀴즈가 지정되지 않았습니다. <a href="/web/">index 로 돌아가기</a></div></div>';
  throw new Error('No quiz parameter');
}

const channelName = `celeb-quiz:${quizName}`;
const sync = new QuizSync(channelName);

let entries = [];
let queue = [];
let cursor = 0;
let revealed = false;
let countdown = initialCountdown;
let countdownTimer = null;
let expired = false;
let started = false;
let playerConnected = false;

const dom = {
  title: document.getElementById('quiz-title'),
  pill: document.getElementById('status-pill'),
  countdown: document.getElementById('countdown'),
  photo: document.getElementById('photo'),
  progress: document.getElementById('progress'),
  name: document.getElementById('name'),
  category: document.getElementById('category'),
  attribution: document.getElementById('attribution'),
  next: document.getElementById('next-btn'),
  reveal: document.getElementById('reveal-btn'),
  restart: document.getElementById('restart-btn'),
  reopen: document.getElementById('reopen-btn'),
  disconnect: document.getElementById('disconnect-notice'),
};

function clampCountdown(n) {
  if (!Number.isFinite(n)) return 7;
  return Math.max(3, Math.min(60, n));
}

async function init() {
  let result;
  try {
    result = await loadQuiz(quizName, QUIZ_BASE);
  } catch (err) {
    dom.title.textContent = `로드 실패: ${err.message}`;
    return;
  }
  entries = result.entries;
  if (entries.length === 0) {
    dom.title.textContent = `${result.manifest.title} — 출제 가능한 인물이 없습니다`;
    return;
  }
  dom.title.textContent = result.manifest.title;
  resetQueue();

  sync.subscribe(EVENTS.PONG, () => {
    const wasDisconnected = !playerConnected;
    playerConnected = true;
    setStatus('연결됨', 'ok');
    hideDisconnect();
    if (wasDisconnected) {
      if (isIdle()) {
        sync.publish(EVENTS.CLOSE, {});
      } else {
        sync.publish(EVENTS.START, currentPayload());
        if (revealed) sync.publish(EVENTS.REVEAL, { entry: serializeEntry(currentEntry()) });
        if (expired) sync.publish(EVENTS.EXPIRED, { entry: serializeEntry(currentEntry()) });
      }
    }
  });
  sync.enableHeartbeat({
    intervalMs: 1000,
    timeoutMs: 3000,
    onTimeout: () => {
      playerConnected = false;
      setStatus('Player 끊김', 'warn');
      showDisconnect();
    },
  });

  dom.next.addEventListener('click', advance);
  dom.reveal.addEventListener('click', revealAnswer);
  dom.restart.addEventListener('click', restart);
  dom.reopen.addEventListener('click', reopenPlayer);

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.code === 'Space') { e.preventDefault(); advance(); }
    else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); revealAnswer(); }
    else if (e.key === 'Escape') { e.preventDefault(); restart(); }
  });

  enterIdleState();
}

function setStatus(text, kind = '') {
  dom.pill.textContent = text;
  dom.pill.classList.remove('ok', 'warn');
  if (kind) dom.pill.classList.add(kind);
}

function showDisconnect() { dom.disconnect.classList.add('shown'); }
function hideDisconnect() { dom.disconnect.classList.remove('shown'); }

function resetQueue() {
  queue = shuffle(entries);
  cursor = -1;
}

function isIdle() {
  return cursor < 0;
}

function currentEntry() {
  return queue[cursor];
}

function currentPayload() {
  return {
    quiz: quizName,
    entry: serializeEntry(currentEntry()),
    countdown,
    index: cursor,
    total: queue.length,
  };
}

function enterIdleState() {
  cursor = -1;
  revealed = false;
  expired = false;
  countdown = initialCountdown;
  started = false;
  stopTimer();
  renderHostUI();
  sync.publish(EVENTS.CLOSE, {});
}

function advance() {
  const wasIdle = isIdle();
  cursor = wasIdle ? 0 : (cursor + 1) % queue.length;
  revealed = false;
  expired = false;
  countdown = initialCountdown;
  started = true;
  renderHostUI();
  sync.publish(wasIdle ? EVENTS.START : EVENTS.NEXT, currentPayload());
  startTimer();
}

function revealAnswer() {
  if (isIdle() || !currentEntry()) return;
  revealed = true;
  renderHostUI();
  sync.publish(EVENTS.REVEAL, { entry: serializeEntry(currentEntry()) });
}

function restart() {
  stopTimer();
  resetQueue();
  expired = false;
  revealed = false;
  countdown = initialCountdown;
  started = false;
  renderHostUI();
  sync.publish(EVENTS.CLOSE, {});
}

function reopenPlayer() {
  const url = `/web/player.html?quiz=${encodeURIComponent(quizName)}&countdown=${initialCountdown}`;
  const w = window.open(url, 'celeb-quiz-player', 'popup,width=1280,height=720');
  if (!w) alert('팝업이 차단되었습니다. 허용 후 다시 시도하세요.');
}

function startTimer() {
  stopTimer();
  countdownTimer = setInterval(tick, 1000);
}
function restartTimer() { startTimer(); }
function stopTimer() { if (countdownTimer) clearInterval(countdownTimer); countdownTimer = null; }

function tick() {
  if (expired) return;
  countdown -= 1;
  if (countdown <= 0) {
    countdown = 0;
    expired = true;
    stopTimer();
    sync.publish(EVENTS.EXPIRED, { entry: serializeEntry(currentEntry()) });
  } else {
    sync.publish(EVENTS.TICK, { remaining: countdown });
  }
  renderHostUI();
}

function renderHostUI() {
  if (isIdle()) {
    dom.countdown.textContent = '–';
    dom.countdown.classList.remove('expired');
    dom.photo.removeAttribute('src');
    dom.photo.alt = '';
    dom.progress.textContent = `0 / ${queue.length} · Next 버튼으로 시작`;
    dom.category.textContent = '';
    dom.name.hidden = true;
    dom.name.textContent = '';
    dom.attribution.innerHTML = '';
    return;
  }
  const e = currentEntry();
  if (!e) return;
  dom.countdown.textContent = expired ? '땡!' : String(countdown);
  dom.countdown.classList.toggle('expired', expired);
  dom.photo.src = `${QUIZ_BASE}/${quizName}/${e.image_path}`;
  dom.photo.alt = e.name;
  dom.progress.textContent = `${cursor + 1} / ${queue.length}`;
  dom.category.textContent = e.category || '';
  dom.name.hidden = false;
  dom.name.textContent = e.name;
  dom.attribution.innerHTML = renderAttribution(e);
}

function renderAttribution(e) {
  if (!e.license) return '';
  const lic = e.license_url
    ? `<a href="${escapeAttr(e.license_url)}" target="_blank" rel="noopener">${escapeHtml(e.license)}</a>`
    : escapeHtml(e.license);
  const artist = e.artist ? `${escapeHtml(e.artist)} · ` : '';
  const src = e.image_source_url
    ? `<a href="${escapeAttr(e.image_source_url)}" target="_blank" rel="noopener">Wikimedia Commons</a>`
    : 'Wikimedia Commons';
  return `${artist}${lic} · ${src}`;
}

function serializeEntry(e) {
  // Player needs the full image URL it can fetch; pass the absolute path.
  return {
    id: e.id,
    name: e.name,
    category: e.category,
    image_url: `${QUIZ_BASE}/${quizName}/${e.image_path}`,
    license: e.license || '',
    license_url: e.license_url || '',
    artist: e.artist || '',
    attribution_html: e.attribution_html || '',
    image_source_url: e.image_source_url || '',
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

window.addEventListener('beforeunload', () => {
  sync.publish(EVENTS.CLOSE, {});
  sync.close();
});

init().catch(err => console.error(err));
