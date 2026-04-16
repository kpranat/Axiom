/**
 * App.jsx — Root component for Axiom.
 * Wires: theme state, useChat hook, Sidebar, ChatPanel.
 * Layout: two-column per wireframe (sidebar | chat panel).
 */

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import MetricsSidebar from './components/MetricsSidebar.jsx'
import Chat from './components/Chat.jsx'
import { useChat } from './hooks/useChat.js'
import LogoDark from './assets/LogoBlack.png'
import LogoLight from './assets/LogoLight.png'
import BgDark from './assets/Bagrounddark.png'
import BgLight from './assets/bagroundLight.png'

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('axiom-theme') || 'light'
  })
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isAppLoading, setIsAppLoading] = useState(true)

  const { messages, sessions, metrics, lastTurn, isLoading, sendMessage, startNewChat, loadSession } = useChat()

  useEffect(() => {
    // Splash screen timer
    const timer = setTimeout(() => {
      setIsAppLoading(false)
    }, 2200)
    return () => clearTimeout(timer)
  }, [])

  function toggleSidebar() {
    setIsSidebarOpen(s => !s)
  }

  /* Apply theme to <html> data-theme attribute */
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('axiom-theme', theme)
  }, [theme])

  function toggleTheme() {
    setTheme(t => (t === 'light' ? 'dark' : 'light'))
  }

  return (
    <div className="app-shell">
      {/* Layer 1 — Background Anchor */}
      <motion.div
        className="bg-anchor"
        initial={{ opacity: 0 }}
        animate={{ opacity: isAppLoading ? 0 : 1 }}
        transition={{ duration: 1.2, ease: 'easeInOut', delay: 0.2 }}
        style={{ backgroundImage: `url(${theme === 'dark' ? BgDark : BgLight})` }}
      />
      {/* Layer 2 — Chameleon Overlay */}
      <motion.div
        className="bg-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: isAppLoading ? 0 : 1 }}
        transition={{ duration: 1.5, ease: 'easeInOut', delay: 0.4 }}
      />

      {/* Layer 3 — UI Content */}
      <AnimatePresence mode="wait">
        {isAppLoading ? (
          <motion.div
            key="splash"
            className="splash-screen"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: 'easeInOut' }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 9999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: theme === 'dark' ? '#111111' : '#f0eeeb',
            }}
          >
            <motion.img
              src={theme === 'dark' ? LogoDark : LogoLight}
              alt="Axiom Logo"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{
                scale: 1,
                opacity: 1,
                rotate: 360
              }}
              transition={{
                scale: { duration: 0.8, ease: 'easeOut' },
                opacity: { duration: 0.8 },
                rotate: { duration: 2, ease: 'linear', repeat: Infinity }
              }}
              style={{ width: '180px', height: 'auto', filter: 'drop-shadow(0 8px 24px rgba(0,0,0,0.15))' }}
            />
          </motion.div>
        ) : (
          <motion.div
            key="app"
            className="app-content"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          >
            <MetricsSidebar
              metrics={metrics}
              lastTurn={lastTurn}
              messages={messages}
              sessions={sessions}
              onNewChat={startNewChat}
              onLoadSession={loadSession}
              isOpen={isSidebarOpen}
              onToggle={toggleSidebar}
              theme={theme}
            />
            <Chat
              messages={messages}
              isLoading={isLoading}
              onSend={sendMessage}
              theme={theme}
              onToggleTheme={toggleTheme}
              isSidebarOpen={isSidebarOpen}
              onToggleSidebar={toggleSidebar}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
