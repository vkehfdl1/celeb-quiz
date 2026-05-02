/**
 * celeb-quiz admin UI controller.
 *
 * Loads quizzes, renders entry cards, wires add/delete/refetch handlers,
 * and listens for clipboard paste events to upload screenshots directly
 * to the selected card. Reuses styles.css + admin.css; no framework.
 *
 * @module admin
 */
import * as api from './admin-api.js';

const QUIZ_BASE = '/data/quizzes';

const state = {
  quizzes: [],
  currentSlug: null,
  manifest: null,
  entries: [],
  filters: { search: '', category: '', status: 'all' },
  selectedId: null,
  pendingOps: new Map(),
  filePickerTarget: null,
};

const dom = {
  quizSelect: document.getElementById('quiz-select'),
  statTotal: document.getElementById('stat-total'),
  statOk: document.getElementById('stat-ok'),
  statFailed: document.getElementById('stat-failed'),
  addForm: document.getElementById('add-form'),
  addName: document.getElementById('add-name'),
  addId: document.getElementById('add-id'),
  addCategory: document.getElementById('add-category'),
  addDisambig: document.getElementById('add-disambig'),
  addAutofetch: document.getElementById('add-autofetch'),
  categoryList: document.getElementById('category-list'),
  filterSearch: document.getElementById('filter-search'),
  filterCategory: document.getElementById('filter-category'),
  filterStatus: document.getElementById('filter-status'),
  filterResultCount: document.getElementById('filter-result-count'),
  grid: document.getElementById('grid'),
  template: document.getElementById('entry-card-tmpl'),
  toasts: document.getElementById('toasts'),
  pasteTarget: document.getElementById('paste-target'),
  filePicker: document.getElementById('file-picker'),
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function slugifyAscii(name) {
  const lower = String(name).trim().toLowerCase();
  if (!lower) return '';
  if (!/^[\x00-\x7f]*$/.test(lower)) return '';
  return lower.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
}

function showToast(message, kind = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  dom.toasts.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function isEntryFailed(entry) {
  if (entry.fetch_status && entry.fetch_status !== 'ok') return true;
  if (!entry.image_path) return true;
  return false;
}

function isEntryOk(entry) {
  return !isEntryFailed(entry);
}

async function init() {
  try {
    const data = await api.listQuizzes();
    state.quizzes = data.quizzes || [];
  } catch (err) {
    showToast(`퀴즈 목록 로드 실패: ${err.message}`, 'error');
    return;
  }

  populateQuizSelect();
  wireEvents();

  if (state.quizzes.length > 0) {
    const firstSlug = state.quizzes[0].name;
    dom.quizSelect.value = firstSlug;
    await loadQuiz(firstSlug);
  }
}

function populateQuizSelect() {
  dom.quizSelect.innerHTML = '';
  if (state.quizzes.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '(등록된 퀴즈 없음)';
    dom.quizSelect.appendChild(opt);
    return;
  }
  for (const q of state.quizzes) {
    const opt = document.createElement('option');
    opt.value = q.name;
    opt.textContent = `${q.title} (${q.count})`;
    dom.quizSelect.appendChild(opt);
  }
}

async function loadQuiz(slug) {
  state.currentSlug = slug;
  state.selectedId = null;
  dom.grid.innerHTML = '<div class="empty-state"><span class="spinner lg"></span></div>';
  try {
    const data = await api.getQuiz(slug);
    state.manifest = data.manifest;
    state.entries = data.entries;
  } catch (err) {
    showToast(`퀴즈 로드 실패: ${err.message}`, 'error');
    return;
  }
  refreshCategories();
  renderStats();
  renderGrid();
}

function refreshCategories() {
  const cats = new Set();
  for (const e of state.entries) {
    if (e.category) cats.add(e.category);
  }
  const sorted = [...cats].sort();

  dom.categoryList.innerHTML = '';
  for (const c of sorted) {
    const opt = document.createElement('option');
    opt.value = c;
    dom.categoryList.appendChild(opt);
  }

  const currentValue = dom.filterCategory.value;
  dom.filterCategory.innerHTML = '<option value="">전체</option>';
  for (const c of sorted) {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    dom.filterCategory.appendChild(opt);
  }
  dom.filterCategory.value = currentValue;
}

function renderStats() {
  const total = state.entries.length;
  const ok = state.entries.filter(isEntryOk).length;
  const failed = total - ok;
  dom.statTotal.textContent = String(total);
  dom.statOk.textContent = String(ok);
  dom.statFailed.textContent = String(failed);
}

function applyFilters(entries) {
  const { search, category, status } = state.filters;
  const needle = search.trim().toLowerCase();
  return entries.filter(e => {
    if (category && e.category !== category) return false;
    if (status === 'ok' && !isEntryOk(e)) return false;
    if (status === 'failed' && !isEntryFailed(e)) return false;
    if (needle) {
      const name = String(e.name || '').toLowerCase();
      const id = String(e.id || '').toLowerCase();
      if (!name.includes(needle) && !id.includes(needle)) return false;
    }
    return true;
  });
}

function renderGrid() {
  const filtered = applyFilters(state.entries);
  dom.filterResultCount.textContent = `${filtered.length} / ${state.entries.length}`;

  dom.grid.innerHTML = '';
  if (filtered.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.innerHTML = '<p>표시할 인물이 없습니다.</p>';
    dom.grid.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  for (const entry of filtered) {
    frag.appendChild(buildCard(entry));
  }
  dom.grid.appendChild(frag);
}

function buildCard(entry) {
  const tmpl = dom.template.content.cloneNode(true);
  const card = tmpl.querySelector('.entry-card');
  card.dataset.id = entry.id;
  card.setAttribute('aria-label', entry.name || entry.id);

  const img = tmpl.querySelector('img');
  const placeholder = tmpl.querySelector('.placeholder');
  if (entry.image_path) {
    const url = `${QUIZ_BASE}/${state.currentSlug}/${entry.image_path}?t=${entry.fetched_at || Date.now()}`;
    img.src = url;
    img.alt = entry.name || entry.id;
    img.onerror = () => {
      img.hidden = true;
      placeholder.hidden = false;
    };
    placeholder.hidden = true;
    img.hidden = false;
  } else {
    img.hidden = true;
    placeholder.hidden = false;
  }

  if (state.pendingOps.has(entry.id)) {
    card.classList.add('pending');
    tmpl.querySelector('.spinner-overlay').hidden = false;
  }

  const pill = tmpl.querySelector('.entry-status-pill');
  if (isEntryOk(entry)) {
    pill.textContent = '✓ OK';
    pill.classList.add('ok');
  } else {
    const status = entry.fetch_status || 'no-image';
    pill.textContent = `✗ ${status}`;
    pill.classList.add('danger');
  }

  tmpl.querySelector('.entry-name').textContent = entry.name || entry.id;
  tmpl.querySelector('.entry-category').textContent = entry.category || '';

  if (entry.id === state.selectedId) {
    card.classList.add('selected');
  }

  card.addEventListener('click', (ev) => {
    if (ev.target.closest('button')) return;
    selectCard(entry.id);
  });
  card.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      selectCard(entry.id);
    }
  });

  for (const btn of tmpl.querySelectorAll('button[data-action]')) {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      selectCard(entry.id);
      handleAction(btn.dataset.action, entry.id);
    });
  }

  return tmpl;
}

function selectCard(id) {
  state.selectedId = id;
  for (const card of dom.grid.querySelectorAll('.entry-card')) {
    card.classList.toggle('selected', card.dataset.id === id);
  }
  dom.pasteTarget.focus({ preventScroll: true });
}

async function handleAction(action, entryId) {
  switch (action) {
    case 'paste':
      showToast('이 카드를 선택했어요. Cmd+V (또는 Ctrl+V)로 붙여넣으세요.', 'success');
      break;
    case 'upload':
      state.filePickerTarget = entryId;
      dom.filePicker.value = '';
      dom.filePicker.click();
      break;
    case 'url': {
      const url = prompt('이미지 URL을 입력하세요:');
      if (url) await uploadFromUrl(entryId, url.trim());
      break;
    }
    case 'refetch':
      await refetchEntry(entryId);
      break;
    case 'delete':
      await deleteEntry(entryId);
      break;
    default:
      console.warn('unknown action', action);
  }
}

function setPending(entryId, op) {
  if (op) {
    state.pendingOps.set(entryId, op);
  } else {
    state.pendingOps.delete(entryId);
  }
  const card = dom.grid.querySelector(`.entry-card[data-id="${CSS.escape(entryId)}"]`);
  if (!card) return;
  card.classList.toggle('pending', op !== null);
  const overlay = card.querySelector('.spinner-overlay');
  if (overlay) overlay.hidden = op === null;
}

function replaceEntry(entry) {
  const idx = state.entries.findIndex(e => e.id === entry.id);
  if (idx >= 0) state.entries[idx] = entry;
  renderStats();
  renderGrid();
}

async function uploadBlob(entryId, blob, filename) {
  if (!state.currentSlug) return;
  setPending(entryId, 'uploading');
  try {
    const result = await api.putImageBlob(state.currentSlug, entryId, blob, filename);
    const entry = state.entries.find(e => e.id === entryId);
    if (entry) {
      entry.image_path = result.image_path;
      entry.image_width = result.image_width;
      entry.image_height = result.image_height;
      entry.fetch_status = 'ok';
      entry.fetched_at = new Date().toISOString();
      replaceEntry(entry);
    }
    showToast(`✓ ${entry?.name || entryId} 사진 업데이트 완료`, 'success');
  } catch (err) {
    showToast(`업로드 실패: ${err.message}`, 'error');
  } finally {
    setPending(entryId, null);
  }
}

async function uploadFromUrl(entryId, url) {
  if (!state.currentSlug) return;
  setPending(entryId, 'uploading');
  try {
    const result = await api.putImageUrl(state.currentSlug, entryId, url);
    const entry = state.entries.find(e => e.id === entryId);
    if (entry) {
      entry.image_path = result.image_path;
      entry.image_width = result.image_width;
      entry.image_height = result.image_height;
      entry.image_source_url = url;
      entry.fetch_status = 'ok';
      entry.fetched_at = new Date().toISOString();
      replaceEntry(entry);
    }
    showToast(`✓ URL에서 사진 다운로드 완료`, 'success');
  } catch (err) {
    showToast(`URL 업로드 실패: ${err.message}`, 'error');
  } finally {
    setPending(entryId, null);
  }
}

async function refetchEntry(entryId) {
  if (!state.currentSlug) return;
  setPending(entryId, 'fetching');
  try {
    const result = await api.refetch(state.currentSlug, entryId);
    if (result && result.entry) {
      replaceEntry(result.entry);
      const status = result.entry.fetch_status || 'unknown';
      showToast(`재검색 완료: ${status}`, status === 'ok' ? 'success' : 'warn');
    }
  } catch (err) {
    showToast(`재검색 실패: ${err.message}`, 'error');
  } finally {
    setPending(entryId, null);
  }
}

async function deleteEntry(entryId) {
  if (!state.currentSlug) return;
  const entry = state.entries.find(e => e.id === entryId);
  const label = entry?.name || entryId;
  if (!confirm(`정말 ${label} 삭제하시겠어요?`)) return;
  setPending(entryId, 'deleting');
  try {
    await api.deleteEntry(state.currentSlug, entryId);
    state.entries = state.entries.filter(e => e.id !== entryId);
    renderStats();
    renderGrid();
    showToast(`✓ ${label} 삭제됨`, 'success');
  } catch (err) {
    showToast(`삭제 실패: ${err.message}`, 'error');
    setPending(entryId, null);
  }
}

async function handleAddSubmit(ev) {
  ev.preventDefault();
  if (!state.currentSlug) {
    showToast('먼저 퀴즈를 선택하세요', 'warn');
    return;
  }
  const name = dom.addName.value.trim();
  const category = dom.addCategory.value.trim();
  const id = dom.addId.value.trim();
  const disambiguation = dom.addDisambig.value.trim();
  const autoFetch = dom.addAutofetch.checked;
  if (!name || !category) {
    showToast('이름과 카테고리는 필수입니다', 'warn');
    return;
  }
  const submitBtn = dom.addForm.querySelector('button[type=submit]');
  submitBtn.disabled = true;
  submitBtn.textContent = autoFetch ? '추가 + 사진 가져오는 중…' : '추가 중…';
  try {
    const result = await api.addEntry(state.currentSlug, {
      name, category, id: id || undefined, disambiguation: disambiguation || undefined, autoFetch,
    });
    state.entries.push(result.entry);
    refreshCategories();
    renderStats();
    renderGrid();
    dom.addForm.reset();
    dom.addAutofetch.checked = true;
    showToast(`✓ ${result.entry.name} 추가됨`, 'success');
  } catch (err) {
    showToast(`추가 실패: ${err.message}`, 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '추가';
  }
}

function wireEvents() {
  dom.quizSelect.addEventListener('change', () => {
    const slug = dom.quizSelect.value;
    if (slug) loadQuiz(slug);
  });

  dom.addName.addEventListener('input', () => {
    if (!dom.addId.value || dom.addId.dataset.userEdited !== 'true') {
      const slug = slugifyAscii(dom.addName.value);
      dom.addId.value = slug;
      dom.addId.dataset.userEdited = 'false';
    }
  });
  dom.addId.addEventListener('input', () => {
    dom.addId.dataset.userEdited = 'true';
  });

  dom.addForm.addEventListener('submit', handleAddSubmit);
  dom.addForm.addEventListener('reset', () => {
    dom.addId.dataset.userEdited = 'false';
    dom.addAutofetch.checked = true;
  });

  dom.filterSearch.addEventListener('input', () => {
    state.filters.search = dom.filterSearch.value;
    renderGrid();
  });
  dom.filterCategory.addEventListener('change', () => {
    state.filters.category = dom.filterCategory.value;
    renderGrid();
  });
  dom.filterStatus.addEventListener('change', () => {
    state.filters.status = dom.filterStatus.value;
    renderGrid();
  });

  dom.filePicker.addEventListener('change', () => {
    const file = dom.filePicker.files && dom.filePicker.files[0];
    if (!file || !state.filePickerTarget) return;
    uploadBlob(state.filePickerTarget, file, file.name);
    state.filePickerTarget = null;
    dom.filePicker.value = '';
  });

  document.addEventListener('paste', (ev) => {
    if (!state.selectedId) {
      showToast('먼저 카드를 클릭해 선택하세요', 'warn');
      return;
    }
    const items = ev.clipboardData ? ev.clipboardData.items : null;
    if (!items) return;
    let imageItem = null;
    for (const item of items) {
      if (item.type && item.type.startsWith('image/')) {
        imageItem = item;
        break;
      }
    }
    if (!imageItem) return;
    ev.preventDefault();
    const blob = imageItem.getAsFile();
    if (!blob) return;
    const ext = (blob.type.split('/')[1] || 'png').toLowerCase().replace('jpeg', 'jpg');
    uploadBlob(state.selectedId, blob, `paste.${ext}`);
  });
}

init().catch(err => {
  console.error(err);
  showToast(`초기화 실패: ${err.message}`, 'error');
});
