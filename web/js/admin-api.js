/**
 * celeb-quiz admin REST client.
 *
 * Thin wrapper around fetch() exposing typed methods for each admin endpoint.
 * All methods return parsed JSON on 2xx, throw AdminApiError on non-2xx.
 *
 * @module admin-api
 */

const API_BASE = '/api';

export class AdminApiError extends Error {
  constructor(status, payload, message) {
    super(message || (payload && payload.error) || ('HTTP ' + status));
    this.name = 'AdminApiError';
    this.status = status;
    this.payload = payload;
  }
}

/**
 * Internal request helper. Returns parsed JSON or throws AdminApiError.
 *
 * @param {string} method
 * @param {string} path
 * @param {{json?: any, formData?: FormData, signal?: AbortSignal}} [opts]
 * @returns {Promise<any>}
 */
async function request(method, path, opts) {
  opts = opts || {};
  var init = { method: method };
  var headers = {};

  if (opts.signal) {
    init.signal = opts.signal;
  }

  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.json);
  } else if (opts.formData) {
    init.body = opts.formData;
  }

  if (Object.keys(headers).length > 0) {
    init.headers = headers;
  }

  var resp;
  try {
    resp = await fetch(API_BASE + path, init);
  } catch (err) {
    throw new AdminApiError(0, null, 'network error: ' + err.message);
  }

  var payload = null;
  var contentType = resp.headers.get('content-type') || '';
  if (contentType.indexOf('application/json') !== -1) {
    try {
      payload = await resp.json();
    } catch (err) {
      payload = null;
    }
  }

  if (!resp.ok) {
    throw new AdminApiError(resp.status, payload, payload && payload.error);
  }

  return payload;
}

/**
 * Fetch the list of all quizzes.
 * @returns {Promise<{quizzes: Array}>}
 */
export function listQuizzes() {
  return request('GET', '/quizzes');
}

/**
 * Fetch full data (manifest + entries) for a quiz.
 * @param {string} slug
 * @returns {Promise<{manifest: object, entries: object[]}>}
 */
export function getQuiz(slug) {
  return request('GET', '/quizzes/' + encodeURIComponent(slug));
}

/**
 * Add a new entry to a quiz.
 * @param {string} slug
 * @param {{name: string, category: string, id?: string, disambiguation?: string, autoFetch?: boolean}} entry
 * @returns {Promise<{entry: object}>}
 */
export function addEntry(slug, entry) {
  var body = {
    name: entry.name,
    category: entry.category,
  };

  if (entry.id) body.id = entry.id;
  if (entry.disambiguation) body.disambiguation = entry.disambiguation;
  if (entry.autoFetch !== undefined) body.auto_fetch = entry.autoFetch;

  return request('POST', '/quizzes/' + encodeURIComponent(slug) + '/entries', { json: body });
}

/**
 * Delete an entry and its image file if present.
 * @param {string} slug
 * @param {string} entryId
 * @returns {Promise<{id: string, removed_image: string | null}>}
 */
export function deleteEntry(slug, entryId) {
  return request(
    'DELETE',
    '/quizzes/' + encodeURIComponent(slug) + '/entries/' + encodeURIComponent(entryId)
  );
}

/**
 * Replace an entry's image by URL.
 * @param {string} slug
 * @param {string} entryId
 * @param {string} url
 * @returns {Promise<{image_path: string, image_width: number, image_height: number}>}
 */
export function putImageUrl(slug, entryId, url) {
  return request(
    'PUT',
    '/quizzes/' + encodeURIComponent(slug) + '/entries/' + encodeURIComponent(entryId) + '/image',
    { json: { url: url } }
  );
}

/**
 * Replace an entry's image by uploading a Blob/File.
 * @param {string} slug
 * @param {string} entryId
 * @param {Blob} blob
 * @param {string} [filename]
 * @returns {Promise<{image_path: string, image_width: number, image_height: number}>}
 */
export function putImageBlob(slug, entryId, blob, filename) {
  var fd = new FormData();
  fd.append('image', blob, filename || 'upload');
  return request(
    'PUT',
    '/quizzes/' + encodeURIComponent(slug) + '/entries/' + encodeURIComponent(entryId) + '/image',
    { formData: fd }
  );
}

/**
 * Re-run the fetch pipeline for a single entry.
 * @param {string} slug
 * @param {string} entryId
 * @returns {Promise<{entry: object}>}
 */
export function refetch(slug, entryId) {
  return request(
    'POST',
    '/quizzes/' + encodeURIComponent(slug) + '/entries/' + encodeURIComponent(entryId) + '/refetch'
  );
}
