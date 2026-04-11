/**
 * client.js — Centralized fetch layer for Axiom frontend.
 * All API calls to the Go backend route through here.
 * Base URL is controlled via VITE_API_URL environment variable.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body) opts.body = JSON.stringify(body)

  const res = await fetch(`${BASE_URL}${path}`, opts)
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
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
