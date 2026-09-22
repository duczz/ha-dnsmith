/* Talking to the hub.
 *
 * Every URL here is RELATIVE. Home Assistant's Ingress serves the add-on
 * under a generated prefix such as /api/hassio_ingress/<token>/, so an
 * absolute "/api/v1/records" would leave the add-on entirely and 404. This is
 * the single most common way an Ingress add-on breaks, and the only defence
 * is to never write a leading slash.
 */

const BASE = new URL('./', document.baseURI);

function url(path, params) {
  const target = new URL(path.replace(/^\/+/, ''), BASE);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== '') {
      target.searchParams.set(key, value);
    }
  }
  return target;
}

export class ApiError extends Error {
  constructor(status, body) {
    const detail = (body && body.error) || {};
    super(detail.message || `HTTP ${status}`);
    this.status = status;
    this.code = detail.code || 'unknown';
    /** Field-level problems, keyed by field id, for form display. */
    this.fields = detail.fields || null;
    this.checks = detail.checks || null;
    this.technical = detail.technical || null;
  }
}

async function request(method, path, { params, body } = {}) {
  let response;
  try {
    response = await fetch(url(path, params), {
      method,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    });
  } catch (cause) {
    throw new ApiError(0, {
      error: {
        code: 'offline',
        message: 'Die Oberfläche erreicht den Hub nicht. Läuft das Add-on noch?',
      },
    });
  }

  if (response.status === 204) return null;

  let payload = null;
  const type = response.headers.get('Content-Type') || '';
  if (type.includes('application/json')) {
    payload = await response.json().catch(() => null);
  }

  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

export const api = {
  status: () => request('GET', 'api/v1/status'),
  records: () => request('GET', 'api/v1/records'),
  record: (id) => request('GET', `api/v1/records/${id}`),
  providers: (query, category) =>
    request('GET', 'api/v1/providers', { params: { q: query, category } }),
  providerForm: (id) => request('GET', `api/v1/providers/${id}`),
  createRecord: (body) => request('POST', 'api/v1/records', { body }),
  patchRecord: (id, body) => request('PATCH', `api/v1/records/${id}`, { body }),
  deleteRecord: (id) => request('DELETE', `api/v1/records/${id}`),
  updateRecord: (id) => request('POST', `api/v1/records/${id}/update`),
  updateAll: () => request('POST', 'api/v1/records/update-all'),
  test: (body) => request('POST', 'api/v1/test', { body }),
  ip: (refresh) => request('GET', 'api/v1/ip', { params: { refresh: refresh ? 'true' : '' } }),
  settings: () => request('GET', 'api/v1/settings'),
  saveSettings: (body) => request('PUT', 'api/v1/settings', { body }),
  exportUrl: (withSecrets) =>
    url('api/v1/config/export', { include_secrets: withSecrets ? 'true' : '' }).toString(),
};
