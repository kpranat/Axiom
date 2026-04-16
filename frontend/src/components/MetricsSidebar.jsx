/**
 * Sidebar.jsx — Left column of the wireframe.
 * Contains: New Chat, Live Token Usage (metrics), Chat History, Account.
 * Animations: Framer Motion drives all open/close transitions — width,
 * inner content fade, and token panel mount/unmount.
 */

import React, { useRef } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import LogoDark from '../assets/LogoBlack.png'
import LogoLight from '../assets/LogoLight.png'

const formatCost = (n) => `$${(n || 0).toFixed(4)}`
const formatNum = (n) => (n || 0).toLocaleString()

/* Spring config shared across sidebar transitions */
const SIDEBAR_SPRING = { type: 'spring', stiffness: 280, damping: 30 }
const FADE_TRANSITION = { duration: 0.18, ease: 'easeOut' }

export default function Sidebar({ metrics, messages, sessions, onNewChat, onLoadSession, isOpen, onToggle, theme, isViewingHistory }) {
  const [searchQuery, setSearchQuery] = React.useState('')
  const [isAccountMenuOpen, setIsAccountMenuOpen] = React.useState(false)
  const [menuRect, setMenuRect] = React.useState(null)
  const [rotationAngle, setRotationAngle] = React.useState(isOpen ? 360 : 0)
  const sidebarRef = React.useRef(null)
  const accountRef = React.useRef(null)
  const menuRef = React.useRef(null)
  const searchInputRef = React.useRef(null)
  const prevOpen = useRef(isOpen)

  const updateMenuPosition = React.useCallback(() => {
    if (accountRef.current && sidebarRef.current) {
      const btnRect = accountRef.current.getBoundingClientRect()
      const sideRect = sidebarRef.current.getBoundingClientRect()
      
      let finalLeft = btnRect.left
      let finalWidth = 220

      if (sideRect.width >= 80) {
        finalLeft = sideRect.left + 8
        finalWidth = sideRect.width - 16
      }

      setMenuRect({
        top: btnRect.top,
        left: finalLeft,
        width: finalWidth
      })
    }
  }, [])

  React.useEffect(() => {
    if (prevOpen.current !== isOpen) {
      prevOpen.current = isOpen
      setRotationAngle(prev => prev + 360)
    }
  }, [isOpen])

  React.useEffect(() => {
    if (!isAccountMenuOpen) return

    function handleDocumentClick(event) {
      const clickedOutsideAccount = accountRef.current && !accountRef.current.contains(event.target)
      const clickedOutsideMenu = menuRef.current && !menuRef.current.contains(event.target)
      
      if (clickedOutsideAccount && clickedOutsideMenu) {
        setIsAccountMenuOpen(false)
      }
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setIsAccountMenuOpen(false)
      }
    }
    
    function handleResize() {
      updateMenuPosition()
    }

    document.addEventListener('mousedown', handleDocumentClick)
    document.addEventListener('keydown', handleKeyDown)
    window.addEventListener('resize', handleResize)
    return () => {
      document.removeEventListener('mousedown', handleDocumentClick)
      document.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('resize', handleResize)
    }
  }, [isAccountMenuOpen])

  const toggleAccountMenu = () => {
    if (!isAccountMenuOpen) {
      updateMenuPosition()
    }
    setIsAccountMenuOpen(prev => !prev)
  }

  /* 
     Search & History Logic:
     1. Merge active session with archived ones for search scope.
     2. If searching, find all matching user messages.
     3. If not searching, just list the sessions by their first user message.
  */
  const activeSessionId = 'active'

  const historyItems = React.useMemo(() => {
    const q = searchQuery.toLowerCase().trim()

    // Archive format is { id, messages, timestamp }
    const allStacks = isViewingHistory
      ? [...sessions]
      : [{ id: activeSessionId, messages: messages }, ...sessions]

    if (q) {
      const results = []
      allStacks.forEach(stack => {
        stack.messages.forEach(m => {
          if (m.role === 'user' && m.content.toLowerCase().includes(q)) {
            results.push({
              sessionId: stack.id,
              msgId: m.id,
              content: m.content,
              isSearchMatch: true
            })
          }
        })
      })
      return results
    }

    // Default: List sessions by first user msg
    return allStacks
      .filter(s => s.messages.length > 0)
      .map(s => ({
        sessionId: s.id,
        content: s.messages.find(m => m.role === 'user')?.content || 'Empty Chat',
        isSearchMatch: false
      }))
  }, [messages, sessions, searchQuery, isViewingHistory])

  return (
    <motion.aside
      ref={sidebarRef}
      aria-label="Sidebar"
      className="sidebar"
      initial={false}
      animate={{ width: isOpen ? 272 : 68 }}
      transition={SIDEBAR_SPRING}
      style={{ overflow: 'hidden', flexShrink: 0 }}
    >
      {/* Header (Logo + Toggle) */}
      <div className="sidebar-logo-container">
        <button
          className="logo-btn"
          onClick={onToggle}
          title={isOpen ? 'Close sidebar' : 'Open sidebar'}
          aria-label={isOpen ? 'Close sidebar' : 'Open sidebar'}
        >
          <motion.img
            src={theme === 'dark' ? LogoDark : LogoLight}
            alt="Logo"
            animate={{ rotate: rotationAngle }}
            transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ scale: 1.12, rotate: rotationAngle + 15, transition: { duration: 0.2 } }}
            whileTap={{ scale: 0.92 }}
            style={{
              height: '36px',
              width: 'auto',
              transformOrigin: 'center',
              filter: theme === 'dark' ? 'brightness(0) invert(1)' : 'none',
            }}
          />
        </button>

        <AnimatePresence>
          {isOpen && (
            <motion.span
              className="sidebar-logo-name"
              key="logo-name"
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={FADE_TRANSITION}
            >
              Axiom
            </motion.span>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {isOpen && (
            <motion.button
              key="close-btn"
              className="sidebar-close-btn"
              onClick={onToggle}
              title="Close sidebar"
              aria-label="Close sidebar"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={FADE_TRANSITION}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* New Chat */}
      <motion.button
        className="btn-action primary-btn"
        onClick={onNewChat}
        aria-label="Start a new chat session"
        whileTap={{ y: 2, scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 400, damping: 17 }}
      >
        <div className="btn-icon-wrapper">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </div>
        <AnimatePresence>
          {isOpen && (
            <motion.span
              key="new-chat-label"
              className="btn-text"
              style={{ fontWeight: 500 }}
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              transition={FADE_TRANSITION}
            >
              New Chat
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>

      {/* Search — stationary icon in both states */}
      <div
        className={isOpen ? "search-bar-inset" : "search-bar-collapsed"}
        aria-label="Search"
        onClick={() => {
          if (!isOpen) {
            onToggle()
          } else {
            searchInputRef.current?.focus()
          }
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          height: '44px',
          width: '100%',
          flexShrink: 0,
          /* padding: 0 ensures the btn-icon-wrapper is at the absolute start */
          padding: 0,
          transition: 'all var(--transition)',
          cursor: !isOpen ? 'pointer' : 'text'
        }}
      >
        <div className="btn-icon-wrapper">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
        <AnimatePresence>
          {isOpen && (
            <motion.input
              key="search-input"
              ref={searchInputRef}
              type="text"
              className="search-input-sk"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -4 }}
              transition={FADE_TRANSITION}
              style={{ flex: 1, minWidth: 0, background: 'transparent', border: 'none', outline: 'none' }}
            />
          )}
        </AnimatePresence>
      </div>

      {/* Chat History */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="chat-history-block"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ ...FADE_TRANSITION, delay: 0.04 }}
            style={{ display: 'flex', flexDirection: 'column', gap: '4px', minHeight: 0, flex: 1 }}
          >
            <div className="sidebar-section-label" aria-hidden="true" style={{ marginTop: '8px' }}>
              {searchQuery ? 'Search Results' : 'Chat History'}
            </div>
            <div className="chat-history-list" role="list" aria-label="Chat history">
              {historyItems.length === 0 ? (
                <div className="chat-history-empty">
                  {searchQuery ? 'No matches found' : 'No messages yet'}
                </div>
              ) : (
                historyItems.map((item, idx) => (
                  <button
                    key={item.sessionId + (item.msgId || idx)}
                    className={`chat-history-item ${item.sessionId === activeSessionId ? 'active' : ''}`}
                    onClick={() => {
                      if (item.sessionId !== activeSessionId) {
                        onLoadSession(item.sessionId)
                        setSearchQuery('')
                      }
                    }}
                    role="listitem"
                    title={item.content}
                    style={{ border: 'none', textAlign: 'left', width: '100%', cursor: 'pointer' }}
                  >
                    {item.content}
                  </button>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Spacer */}
      <div style={{ flex: 1, minHeight: 0 }} />

      {/* Live Token Usage — mounts/unmounts smoothly */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="metrics"
            className="metrics-panel-sk"
            role="region"
            aria-label="Live Token Usage"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            <div className="metrics-panel-title-sk">
              <motion.span
                className="metrics-live-dot-sk"
                aria-hidden="true"
                animate={{
                  scale: [1, 1.25, 1],
                  opacity: [0.6, 1, 0.6],
                  boxShadow: [
                    '0 0 0 0 rgba(0,0,0,0)',
                    '0 0 0 3px rgba(0,0,0,0.12)',
                    '0 0 0 0 rgba(0,0,0,0)',
                  ],
                }}
                transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
              />
              Live Token Usage
            </div>
            <MetricRow label="Tokens Used" value={formatNum(metrics.tokens_used)} />
            <MetricRow label="Tokens Saved" value={formatNum(metrics.tokens_saved)} />
            <MetricRow label="Cache Hits" value={formatNum(metrics.cache_hits)} />
            <MetricRow label="Cache Misses" value={formatNum(metrics.cache_misses)} />
            <MetricRow label="Cost Saved" value={formatCost(metrics.cost_saved)} isAccent />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Account */}
      <div ref={accountRef} style={{ position: 'relative' }}>
        <button
          className="account-btn-sk"
          aria-label="Account settings"
          onClick={toggleAccountMenu}
        >
          <div className="account-avatar-sk" aria-hidden="true">{avatarLetter(user)}</div>
          <AnimatePresence>
            {isOpen && (
              <motion.div
                key="account-info"
                className="account-info-sk"
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6 }}
                transition={FADE_TRANSITION}
              >
                <div className="account-name-sk">{displayName(user)}</div>
                <div className="account-plan-sk">{(user?.plan || 'free').toUpperCase()} plan</div>
              </motion.div>
            )}
          </AnimatePresence>
        </button>

        {createPortal(
          <AnimatePresence>
            {isAccountMenuOpen && menuRect && (
              <motion.div
                ref={menuRef}
                key="account-dropdown"
                className="profile-dropdown-menu"
                initial={{ opacity: 0, y: 8, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1, transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] } }}
                exit={{ opacity: 0, y: 6, scale: 0.97, transition: { duration: 0.15, ease: 'easeIn' } }}
                style={{
                  position: 'fixed',
                  left: menuRect.left,
                  width: menuRect.width,
                  bottom: window.innerHeight - menuRect.top + 8,
                  zIndex: 99999,
                }}
              >
                <div className="profile-dropdown-header">
                  <div className="account-avatar-sk" style={{ width: 32, height: 32, fontSize: 13 }} aria-hidden="true">{avatarLetter(user)}</div>
                  <div className="profile-dropdown-user-info">
                    <div className="profile-dropdown-email">{displayName(user)}</div>
                    <div className="profile-dropdown-plan">{(user?.plan || 'free').toUpperCase()} plan</div>
                  </div>
                </div>
                <div className="profile-dropdown-divider" style={{ marginTop: 0, paddingTop: 0 }}></div>
                
                <button className="profile-dropdown-item" onClick={() => setIsAccountMenuOpen(false)}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                  Profile
                  <span className="profile-dropdown-chevron">›</span>
                </button>
                <button className="profile-dropdown-item" onClick={() => setIsAccountMenuOpen(false)}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                  Settings
                  <span className="profile-dropdown-chevron">›</span>
                </button>
                <button className="profile-dropdown-item" onClick={() => setIsAccountMenuOpen(false)}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                  Help
                </button>
                <div className="profile-dropdown-divider"></div>
                <button
                  className="profile-dropdown-item logout-item"
                  onClick={async () => {
                    setIsAccountMenuOpen(false)
                    if (onLogout) {
                      await onLogout()
                    }
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                  Logout
                </button>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body
        )}
      </div>
    </motion.aside>
  )
}

  function displayName(user) {
    if (!user) return 'User'
    if (user.name) return user.name
    if (user.email) return user.email
    return 'User'
  }

  function avatarLetter(user) {
    const source = displayName(user)
    const letter = source.trim().charAt(0)
    return (letter || 'U').toUpperCase()
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
