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
  const [sessions, setSessions] = useState([])
  const [metrics, setMetrics] = useState(INITIAL_METRICS)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  /* ── Create session on mount ── */
  useEffect(() => {
    initSession()
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
    } catch {
      // Backend not available — generate a local session id for demo
      setSessionId(`local-${Date.now()}`)
    }
  }

  const sendMessage = useCallback(async (prompt) => {
    if (!prompt.trim() || isLoading) return
    setError(null)

    const userMsg = { id: Date.now(), role: 'user', content: prompt }
    setMessages(prev => [...prev, userMsg])
    setIsLoading(true)

    try {
      const data = await sendChat(sessionId, prompt)
      const aiMsg = {
        id: Date.now() + 1,
        role: 'ai',
        content: data.response,
        model_used: data.model_used,
        tokens_used: data.tokens_used,
        tokens_saved: data.tokens_saved,
        cache_hit: data.cache_hit,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (err) {
      // Graceful mock response when backend is offline
      const mockMsg = {
        id: Date.now() + 1,
        role: 'ai',
        content: `[Backend offline — mock response] You asked: "${prompt}"`,
        model_used: 'gpt-3.5-turbo',
        tokens_used: 42,
        tokens_saved: 0,
        cache_hit: false,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, mockMsg])
    } finally {
      setIsLoading(false)
    }
  }, [sessionId, isLoading])

  const startNewChat = useCallback(() => {
    // Only archive if there are actual messages
    if (messages.length > 0) {
      setSessions(prev => [
        { id: Date.now(), messages: [...messages], timestamp: new Date() },
        ...prev
      ])
    }
    setMessages([])
    setMetrics(INITIAL_METRICS)
    clearInterval(pollRef.current)
    initSession()
  }, [messages])

  const loadSession = useCallback((sessionIdToLoad) => {
    const session = sessions.find(s => s.id === sessionIdToLoad)
    if (session) {
      // Archive current messages first if needed, though usually user clicks history from an empty state or wants to swap
      if (messages.length > 0) {
        setSessions(prev => [
          { id: Date.now(), messages: [...messages], timestamp: new Date() },
          ...prev.filter(s => s.id !== sessionIdToLoad)
        ])
      }
      setMessages(session.messages)
    }
  }, [sessions, messages])

  return { messages, sessions, metrics, isLoading, error, sessionId, sendMessage, startNewChat, loadSession }
}
