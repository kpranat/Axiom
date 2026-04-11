/**
 * Sidebar.jsx — Left column of the wireframe.
 * Contains: New Chat, Live Token Usage (metrics), Chat History, Account.
 */

import React from 'react'

const formatCost = (n) => `$${(n || 0).toFixed(4)}`
const formatNum = (n) => (n || 0).toLocaleString()

export default function Sidebar({ metrics, messages, onNewChat, isOpen, onToggle }) {
  /* Derive chat history from message pairs (user messages only for labels) */
  const history = messages
    .filter(m => m.role === 'user')
    .slice()
    .reverse()
    .slice(0, 20)

  return (
    <aside className={`sidebar ${!isOpen ? 'closed' : ''}`} aria-label="Sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="sidebar-logo-icon" aria-hidden="true">Ax</div>
          <span className="sidebar-logo-name">Axiom</span>
        </div>
        <button 
          className="sidebar-close-btn" 
          onClick={onToggle}
          title="Close sidebar"
          aria-label="Close sidebar"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* New Chat */}
      <button
        id="btn-new-chat"
        className="btn-new-chat"
        onClick={onNewChat}
        aria-label="Start a new chat session"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New Chat
      </button>

      {/* Live Token Usage */}
      <div className="metrics-panel" role="region" aria-label="Live Token Usage">
        <div className="metrics-panel-title">
          <span className="metrics-live-dot" aria-hidden="true" />
          Live Token Usage
        </div>

        <MetricRow label="Tokens Used" value={formatNum(metrics.tokens_used)} />
        <MetricRow label="Tokens Saved" value={formatNum(metrics.tokens_saved)} />
        <MetricRow label="Cache Hits" value={formatNum(metrics.cache_hits)} />
        <MetricRow label="Cache Misses" value={formatNum(metrics.cache_misses)} />
        <MetricRow label="Cost Saved" value={formatCost(metrics.cost_saved)} />
      </div>

      {/* Chat History */}
      <div className="sidebar-section-label" aria-hidden="true">Chat History</div>
      <div className="chat-history-list" role="list" aria-label="Chat history">
        {history.length === 0 ? (
          <div className="chat-history-empty">No messages yet</div>
        ) : (
          history.map((msg, i) => (
            <div
              key={msg.id}
              className={`chat-history-item${i === 0 ? ' active' : ''}`}
              role="listitem"
              title={msg.content}
            >
              {msg.content}
            </div>
          ))
        )}
      </div>

      {/* Account */}
      <button
        id="btn-account"
        className="account-btn"
        aria-label="Account settings"
      >
        <div className="account-avatar" aria-hidden="true">U</div>
        <div className="account-info">
          <div className="account-name">User</div>
          <div className="account-plan">Hackathon Demo</div>
        </div>
      </button>
    </aside>
  )
}

function MetricRow({ label, value }) {
  const [animated, setAnimated] = React.useState(false)
  const prevVal = React.useRef(value)

  React.useEffect(() => {
    if (prevVal.current !== value) {
      setAnimated(true)
      prevVal.current = value
      const t = setTimeout(() => setAnimated(false), 450)
      return () => clearTimeout(t)
    }
  }, [value])

  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <span className={`metric-value${animated ? ' updated' : ''}`}>{value}</span>
    </div>
  )
}
