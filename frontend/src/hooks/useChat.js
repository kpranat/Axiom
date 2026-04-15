/**
 * useChat.js — Custom hook managing chat state, session, and API calls.
 * Per PRD: session_id is created on mount; metrics poll every 2 seconds.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { createSession, sendChat, getMetrics } from '../api/client.js'

const METRICS_POLL_INTERVAL = 2000

const INITIAL_METRICS = {
  tokens_used: 0,
  tokens_saved: 0,
  cache_hits: 0,
  cache_misses: 0,
  cost_saved: 0,
}

export function useChat() {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [metrics, setMetrics] = useState(INITIAL_METRICS)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  /* ── Create session on mount ── */
  useEffect(() => {
    initSession().catch(() => {
      // Initial session setup failure is surfaced via error state.
    })
    return () => clearInterval(pollRef.current)
  }, [])

  /* ── Start metrics polling once session is ready ── */
  useEffect(() => {
    if (!sessionId) return
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const data = await getMetrics(sessionId)
        setMetrics(data)
      } catch {
        // silent — backend may not be running; use mock data
      }
    }, METRICS_POLL_INTERVAL)
    return () => clearInterval(pollRef.current)
  }, [sessionId])

  async function initSession() {
    try {
      const data = await createSession()
      setSessionId(data.session_id)
      setError(null)
      return data.session_id
    } catch (err) {
      setSessionId(null)
      setError(err instanceof Error ? err.message : 'Failed to create session')
      throw err
    }
  }

  const sendMessage = useCallback(async (prompt) => {
    if (!prompt.trim() || isLoading) return
    setError(null)

    const userMsg = { id: Date.now(), role: 'user', content: prompt }
    setMessages(prev => [...prev, userMsg])
    setIsLoading(true)

    try {
      let activeSessionId = sessionId
      if (!activeSessionId) {
        activeSessionId = await initSession()
      }

      if (!activeSessionId) {
        throw new Error('Session is not available')
      }

      const data = await sendChat(activeSessionId, prompt)
      const aiMsg = {
        id: Date.now() + 1,
        role: 'ai',
        content: data.response,
        model_used: data.model_used,
        tokens_used: data.tokens_used,
        tokens_saved: data.tokens_saved,
        total_tokens_used: data.total_tokens_used,
        cache_hit: data.cache_hit,
        token_breakdown: data.token_breakdown,
        workflow: data.workflow,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Request failed'
      setError(message)

      const errorMsg = {
        id: Date.now() + 1,
        role: 'ai',
        content: `[Request failed] ${message}`,
        model_used: 'gateway-error',
        tokens_used: 0,
        tokens_saved: 0,
        total_tokens_used: 0,
        cache_hit: false,
        token_breakdown: null,
        workflow: null,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
    }
  }, [sessionId, isLoading])

  const startNewChat = useCallback(() => {
    setMessages([])
    setMetrics(INITIAL_METRICS)
    clearInterval(pollRef.current)
    initSession()
  }, [])

  return { messages, metrics, isLoading, error, sessionId, sendMessage, startNewChat }
}
