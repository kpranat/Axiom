/**
 * Sidebar.jsx — Left column of the wireframe.
 * Contains: New Chat, Live Token Usage (metrics), Chat History, Account.
 */

import React, { useRef } from 'react'
import { motion, AnimatePresence, useAnimationControls } from 'framer-motion'
import Logo from '../assets/Adobe Express - file.png'

const formatCost = (n) => `$${(n || 0).toFixed(4)}`
const formatNum = (n) => (n || 0).toLocaleString()

export default function Sidebar({ metrics, messages, onNewChat, isOpen, onToggle }) {
  const logoControls = useAnimationControls()
  const prevOpen = useRef(isOpen)

  React.useEffect(() => {
    if (prevOpen.current !== isOpen) {
      prevOpen.current = isOpen
      logoControls.start({
        rotate: isOpen ? 360 : 0,
        transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] }
      })
    }
  }, [isOpen, logoControls])

  /* Derive chat history from message pairs. To represent the current session, only use the very first user message. */
  const firstUserMsg = messages.find(m => m.role === 'user')
  const history = firstUserMsg ? [firstUserMsg] : []

  return (
    <aside className={`sidebar ${!isOpen ? 'closed' : ''}`} aria-label="Sidebar">
      {/* Header (Logo + Toggle) */}
      <div className="sidebar-logo-container">
        <button 
          className="logo-btn" 
          onClick={onToggle}
          title={isOpen ? "Close sidebar" : "Open sidebar"}
          aria-label={isOpen ? "Close sidebar" : "Open sidebar"}
        >
          <motion.img
            src={Logo}
            alt="Logo"
            animate={logoControls}
            whileHover={{ scale: 1.12, rotate: 15, transition: { duration: 0.2 } }}
            whileTap={{ scale: 0.92 }}
            style={{ height: '36px', width: 'auto', transformOrigin: 'center' }}
          />
        </button>
        <span className="sidebar-logo-name">Axiom</span>
        <button 
          className="sidebar-close-btn" 
          onClick={onToggle}
          title="Close sidebar"
          aria-label="Close sidebar"
          style={{ visibility: isOpen ? 'visible' : 'hidden' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* New Chat */}
      <button className="btn-action primary" onClick={onNewChat} aria-label="Start a new chat session">
        <div className="btn-icon-wrapper">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </div>
        <span className="btn-text">New Chat</span>
      </button>

      {/* Search */}
      <button className="btn-action" aria-label="Search">
        <div className="btn-icon-wrapper">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
        <span className="btn-text">Search</span>
      </button>

      {/* Chat History */}
      <div className="sidebar-section-label" aria-hidden="true" style={{ marginTop: '8px' }}>Chat History</div>
      <div className="chat-history-list" role="list" aria-label="Chat history">
        {history.length === 0 ? (
          <div className="chat-history-empty">No messages yet</div>
        ) : (
          history.map((msg, i) => (
            <div
              key={msg.id}
              className="chat-history-item active"
              role="listitem"
              title={msg.content}
            >
              {msg.content}
            </div>
          ))
        )}
      </div>

      {/* Spacer */}
      <div style={{ flex: 1, minHeight: 0 }} />

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
        <MetricRow label="Cost Saved" value={formatCost(metrics.cost_saved)} isAccent />
      </div>

      {/* Account */}
      <button className="account-btn" aria-label="Account settings">
        <div className="account-avatar" aria-hidden="true">U</div>
        <div className="account-info">
          <div className="account-name">User</div>
          <div className="account-plan">Hackathon Demo</div>
        </div>
      </button>
    </aside>
  )
}

function MetricRow({ label, value, isAccent }) {
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
      <span className={`metric-value${animated ? ' updated' : ''}${isAccent ? ' accent' : ''}`}>{value}</span>
    </div>
  )
}
