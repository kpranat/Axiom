/**
 * client.js — Centralized fetch layer for Axiom frontend.
 * All API calls to the Go backend route through here.
 * Default base path is /api so Vite can proxy requests to Go in dev.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '/api'

function buildURL(path) {
  const normalizedBase = BASE_URL.endsWith('/') ? BASE_URL.slice(0, -1) : BASE_URL
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${normalizedBase}${normalizedPath}`
}

async function parseError(res) {
  const text = await res.text()
  if (!text) return `HTTP ${res.status}`

  try {
    const payload = JSON.parse(text)
    if (payload && typeof payload.error === 'string' && payload.error.trim()) {
      return payload.error
    }
  } catch {
    // Response body is plain text.
  }

  return text
}

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: {},
  }
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(buildURL(path), opts)
  if (!res.ok) {
    throw new Error(await parseError(res))
  }
  return res.json()
}

/**
 * POST /session — Create a new session.
 * Returns: { session_id: string }
 */
export async function createSession() {
  return request('POST', '/session')
}

/**
 * POST /chat — Send a prompt to the orchestrator.
 * Body: { prompt: string, session_id: string }
 * Returns: { response, model_used, tokens_used, tokens_saved, cache_hit }
 */
export async function sendChat(sessionId, prompt) {
  return request('POST', '/chat', { session_id: sessionId, prompt })
}

/**
 * GET /metrics/:session_id — Fetch live token counters.
 * Returns: { tokens_used, tokens_saved, cache_hits, cache_misses, cost_saved }
 */
export async function getMetrics(sessionId) {
  return request('GET', `/metrics/${sessionId}`)
}
