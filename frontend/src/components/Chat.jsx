/**
 * ChatPanel.jsx — Main chat interface.
 * Contains: top bar with ThemeToggle, message area, input + model selector.
 * Per wireframe: "What can i do for you?" welcome, chat input, Model dropdown.
 */

import { useRef, useEffect, useState } from 'react'
import Message from './Message.jsx'
import ThemeToggle from './ThemeToggle.jsx'

const MODEL_OPTIONS = [
  { value: 'auto', label: 'Auto (Cascade)' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'gpt-4o', label: 'GPT-4o' },
]

export default function ChatPanel({ messages, isLoading, onSend, theme, onToggleTheme, isSidebarOpen, onToggleSidebar }) {
  const [input, setInput] = useState('')
  const [model, setModel] = useState('auto')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  /* Auto-scroll to bottom on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  /* Auto-resize textarea */
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
  }, [input])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const hasMessages = messages.length > 0

  return (
    <main className={`chat-panel ${!hasMessages ? 'empty-state' : ''}`} role="main">
      {/* Top bar */}
      <div className="chat-topbar">
        {!isSidebarOpen && (
          <button 
            className="sidebar-open-btn" 
            onClick={onToggleSidebar}
            title="Open sidebar"
            aria-label="Open sidebar"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
        )}
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>

      {/* Messages */}
      <div className="messages-area" role="log" aria-live="polite" aria-label="Chat messages">
        {!hasMessages ? (
          <Welcome />
        ) : (
          <>
            {messages.map(msg => (
              <Message key={msg.id} message={msg} />
            ))}
            {isLoading && (
              <div className="message-wrapper ai">
                <div className="thinking-dots" role="status" aria-label="Axiom is thinking">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {/* Input Area */}
      <div className="input-area">
        <div className="input-container">
          <div className="input-row">
            <textarea
              id="chat-input"
              ref={textareaRef}
              className="chat-textarea"
              placeholder="What can I help you with?"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              aria-label="Chat input"
              disabled={isLoading}
            />
            <button
              id="btn-send"
              className="send-btn"
              onClick={submit}
              disabled={!input.trim() || isLoading}
              aria-label="Send message"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>

          {/* Model Selector — per wireframe */}
          <div className="input-footer">
            <label className="model-select-label" htmlFor="model-select">Model</label>
            <select
              id="model-select"
              className="model-select"
              value={model}
              onChange={e => setModel(e.target.value)}
              aria-label="Select model"
            >
              {MODEL_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </main>
  )
}

function Welcome() {
  return (
    <div className="chat-welcome" role="presentation">
      <div className="chat-welcome-icon" aria-hidden="true">✦</div>
      <h2>What can i do for you?</h2>
      <p>
        Ask anything. Axiom routes your query through a semantic cache and
        model cascade to minimize token cost automatically.
      </p>
    </div>
  )
}
