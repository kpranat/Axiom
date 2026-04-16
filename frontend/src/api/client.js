import { requestJSON } from '../lib/api.js'

/**
 * POST /session — Create a new session.
 * Returns: { session_id: string }
 */
export async function createSession() {
  return requestJSON('/api/session', { method: 'POST' })
}

/**
 * POST /chat — Send a prompt to the orchestrator.
 * Body: { prompt: string, session_id: string }
 * Returns: { response, model_used, tokens_used, tokens_saved, cache_hit }
 */
export async function sendChat(sessionId, prompt) {
  return requestJSON('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, prompt }),
  })
}

/**
 * GET /metrics/:session_id — Fetch live token counters.
 * Returns: { tokens_used, tokens_saved, cache_hits, cache_misses, cost_saved }
 */
export async function getMetrics(sessionId) {
  return requestJSON(`/api/metrics/${sessionId}`, { method: 'GET' })
}
