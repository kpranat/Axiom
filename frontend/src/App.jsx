/**
 * App.jsx — Root component for Axiom.
 * Wires: theme state, useChat hook, Sidebar, ChatPanel.
 * Layout: two-column per wireframe (sidebar | chat panel).
 */

import { useState, useEffect } from 'react'
import MetricsSidebar from './components/MetricsSidebar.jsx'
import Chat from './components/Chat.jsx'
import { useChat } from './hooks/useChat.js'

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('axiom-theme') || 'light'
  })
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)

  const { messages, metrics, isLoading, sendMessage, startNewChat } = useChat()

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
      <MetricsSidebar
        metrics={metrics}
        messages={messages}
        onNewChat={startNewChat}
        isOpen={isSidebarOpen}
        onToggle={toggleSidebar}
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
    </div>
  )
}
