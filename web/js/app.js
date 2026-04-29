import { loadIndex, QuizLoadError } from './quiz-loader.js';

const QUIZ_BASE = '/data/quizzes';
const DEFAULT_COUNTDOWN = 7;

let selectedQuiz = null;
let allQuizzes = [];

// Latest in-flight quiz.json fetch. A new card click aborts the previous
// fetch so the countdown input always reflects the most recent selection.
let pendingDefaultsAbort = null;

/**
 * Boot the landing page: load index, render quiz cards, wire selection +
 * Start button. All errors fall through to the catch handler at the bottom
 * which paints an empty-state instead of leaving a blank page.
 */
async function init() {
  const grid = document.getElementById('quiz-grid');
  const settings = document.getElementById('settings');
  const startBtn = document.getElementById('start-btn');
  const startHint = document.getElementById('start-hint');
  const countdownInput = document.getElementById('countdown');

  countdownInput.value = String(DEFAULT_COUNTDOWN);

  try {
    const idx = await loadIndex(QUIZ_BASE);
    allQuizzes = idx.quizzes || [];
  } catch (err) {
    grid.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = '퀴즈 인덱스를 불러오지 못했습니다.';
    const detail = document.createElement('div');
    detail.className = 'muted';
    detail.textContent = err.message;
    empty.appendChild(document.createElement('br'));
    empty.appendChild(detail);
    grid.appendChild(empty);
    return;
  }

  if (allQuizzes.length === 0) {
    grid.innerHTML = `<div class="empty-state">
      <p>등록된 퀴즈가 없습니다.</p>
      <p class="muted">
        에이전트에게 <code>celeb-quiz-listup</code> 스킬을 요청해서 인물 목록을 만든 뒤,
        <code>celeb-quiz-image</code>로 사진을 가져오고
        <code>celeb-quiz-setup</code>으로 등록하세요.
      </p>
    </div>`;
    return;
  }

  for (const q of allQuizzes) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'quiz-card';
    card.dataset.name = q.name;
    card.innerHTML = `
      <h3></h3>
      <div class="meta">
        <span class="count"></span>
        <span class="category"></span>
      </div>
    `;
    card.querySelector('h3').textContent = q.title || q.name;
    const count = q.valid_count ?? q.count ?? 0;
    card.querySelector('.count').textContent = `${count}문제`;
    card.querySelector('.category').textContent = q.category || '';
    card.addEventListener('click', () => selectQuiz(q));
    grid.appendChild(card);
  }

  settings.hidden = false;

  startBtn.addEventListener('click', () => {
    if (!selectedQuiz) return;
    const n = clampCountdown(parseInt(countdownInput.value, 10));
    const params = new URLSearchParams({
      quiz: selectedQuiz.name,
      countdown: String(n),
    });
    // Open the Player popup FIRST, inside the click handler's user-gesture
    // window. Browsers block window.open() that runs after an await or in a
    // detached callback. Abort if blocked so the user can retry.
    const playerUrl = `/web/player.html?${params}`;
    const playerWin = window.open(
      playerUrl,
      'celeb-quiz-player',
      'popup,width=1280,height=720',
    );
    if (!playerWin) {
      alert('팝업이 차단되어 Player 창을 열 수 없습니다. 팝업 허용 후 다시 시도하세요.');
      return;
    }
    location.href = `/web/host.html?${params}`;
  });

  function selectQuiz(q) {
    selectedQuiz = q;
    document.querySelectorAll('.quiz-card').forEach((c) => {
      c.classList.toggle('selected', c.dataset.name === q.name);
    });
    startBtn.disabled = false;
    startHint.textContent = `선택됨: ${q.title || q.name}`;
    countdownInput.value = String(DEFAULT_COUNTDOWN);

    if (pendingDefaultsAbort) pendingDefaultsAbort.abort();
    const ctrl = new AbortController();
    pendingDefaultsAbort = ctrl;
    fetchDefaultCountdown(q.name, ctrl.signal)
      .then((seconds) => {
        if (ctrl.signal.aborted) return;
        if (selectedQuiz !== q) return;
        countdownInput.value = String(clampCountdown(seconds));
      })
      .catch((err) => {
        if (err && err.name === 'AbortError') return;
        console.warn(`[app] default_countdown_seconds fallback for ${q.name}:`, err);
      });
  }
}

async function fetchDefaultCountdown(name, signal) {
  const url = `${QUIZ_BASE}/${name}/quiz.json`;
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new QuizLoadError(`Failed to fetch ${url}: HTTP ${res.status}`);
  }
  const data = await res.json();
  const v = Number(data && data.default_countdown_seconds);
  return Number.isFinite(v) && v > 0 ? v : DEFAULT_COUNTDOWN;
}

function clampCountdown(n) {
  if (!Number.isFinite(n)) return DEFAULT_COUNTDOWN;
  return Math.max(3, Math.min(60, Math.round(n)));
}

init().catch((err) => {
  console.error(err);
  document.body.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.className = 'container';
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.textContent = `초기화 실패: ${err && err.message ? err.message : String(err)}`;
  wrap.appendChild(empty);
  document.body.appendChild(wrap);
});
