/**
 * ChatPanel.jsx — Main chat interface.
 * Contains: top bar with ThemeToggle, message area, input + model selector.
 * Per wireframe: "What can i do for you?" welcome, chat input, Model dropdown.
 */

import { useRef, useEffect, useState } from 'react'
import { motion, useAnimationControls } from 'framer-motion'
import Message from './Message.jsx'
import ThemeToggle from './ThemeToggle.jsx'
import LogoDark from '../assets/LogoBlack.png'
import LogoLight from '../assets/LogoLight.png'

export default function ChatPanel({ messages, isLoading, onSend, theme, onToggleTheme, isSidebarOpen, onToggleSidebar }) {
  const [input, setInput] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  /* Clear local submission lock when parent loading state finishes */
  useEffect(() => {
    if (!isLoading) {
      setIsSubmitting(false)
    }
  }, [isLoading])

  /* Auto-scroll to bottom on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })

    // If the last message is from AI, we are animating the reveal
    const lastMsg = messages[messages.length - 1]
    if (lastMsg && lastMsg.role === 'ai') {
      setIsAnimating(true)
    }
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
      if (!isLoading && !isSubmitting && !isAnimating) {
        submit()
      }
    }
  }

  function submit() {
    const trimmed = input.trim()
    if (!trimmed || isLoading || isSubmitting || isAnimating) return
    setIsSubmitting(true)
    onSend(trimmed)
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const hasMessages = messages.length > 0

  return (
    <main
      className={`chat-panel ${!hasMessages ? 'empty-state' : ''}`}
      role="main"
    >
      {/* Top bar */}
      <div className="chat-topbar">
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>

      {/* Messages */}
      <div
        className="messages-area"
        role="log"
        aria-live="polite"
        aria-label="Chat messages"
      >
        {!hasMessages ? (
          <Welcome theme={theme} />
        ) : (
          <>
            {messages.map((msg, i) => (
              <Message
                key={msg.id}
                message={msg}
                onAnimationComplete={i === messages.length - 1 ? () => setIsAnimating(false) : undefined}
              />
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
        <div className="input-container-sk">
          <div className="input-row">
            <div style={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'flex-start' }}>
              {!input && !hasMessages && (
                <motion.div
                  style={{
                    position: 'absolute',
                    left: 0,
                    top: '2px', // matches textarea's 2px padding
                    pointerEvents: 'none',
                    color: 'var(--text-placeholder)',
                    display: 'flex',
                    gap: '4px',
                    fontSize: '14px',
                    fontFamily: 'var(--font-sans)',
                    lineHeight: '1.5',
                    zIndex: 1
                  }}
                  initial="hidden"
                  animate="visible"
                  variants={{
                    hidden: { opacity: 0 },
                    visible: { opacity: 1, transition: { staggerChildren: 0.1, delayChildren: 1.2 } }
                  }}
                  aria-hidden="true"
                >
                  {"What can I help you with?".split(' ').map((word, i) => (
                    <motion.span
                      key={i}
                      variants={{
                        hidden: { opacity: 0, y: 6, filter: 'blur(2px)' },
                        visible: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.4, ease: 'easeOut' } }
                      }}
                      style={{ display: 'inline-block' }}
                    >
                      {word}
                    </motion.span>
                  ))}
                </motion.div>
              )}
              <textarea
                id="chat-input"
                ref={textareaRef}
                className="chat-textarea"
                placeholder={hasMessages ? "Reply..." : ""}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                aria-label="Chat input"
                style={{ zIndex: 2, position: 'relative', width: '100%' }}
              />
            </div>
            <button
              id="btn-send"
              className="send-btn-sk"
              onClick={submit}
              disabled={!input.trim() || isLoading || isSubmitting || isAnimating}
              aria-label="Send message"
              style={{ zIndex: 2 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>

        </div>
      </div>
    </main>
  )
}

const TIME_MESSAGES = {
  morning: [
    "Fresh start today",
    "Let's begin",
    "Morning clarity",
    "Good to see you",
    "What's on your mind",
  ],
  afternoon: [
    "Keep it moving",
    "In the flow",
    "Still going strong",
    "What's next",
    "Ready when you are",
  ],
  evening: [
    "Take it easy",
    "Calm evening",
    "Winding down",
    "How's it going",
    "What can I help with",
  ],
  night: [
    "Hello, night owl",
    "Still awake",
    "Quiet hours",
    "Late night thoughts",
    "Burning the midnight oil",
  ],
}

function getTimePeriod() {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 12) return 'morning'
  if (hour >= 12 && hour < 17) return 'afternoon'
  if (hour >= 17 && hour < 21) return 'evening'
  return 'night'
}

function pickMessage(period) {
  const pool = TIME_MESSAGES[period]
  return pool[Math.floor(Math.random() * pool.length)]
}

function Welcome({ theme }) {
  const [greeting] = useState(() => pickMessage(getTimePeriod()))
  const spinControls = useAnimationControls()
  const isSpinning = useRef(false)

  async function handleClick() {
    if (isSpinning.current) return
    isSpinning.current = true

    await spinControls.start({
      scale: 0.95,
      rotate: 360,
      transition: { duration: 1.4, ease: 'easeInOut' }
    })

    spinControls.set({ rotate: 0 })

    // Scale back up cleanly
    await spinControls.start({
      scale: 1,
      transition: { duration: 0.4, ease: 'easeOut' }
    })

    isSpinning.current = false
  }

  // Split greeting into words for word-by-word animation
  const words = greeting.split(' ')

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.12,
        delayChildren: 0.3
      }
    }
  }

  const wordVariants = {
    hidden: { opacity: 0, y: 10, filter: 'blur(4px)' },
    visible: {
      opacity: 1,
      y: 0,
      filter: 'blur(0px)',
      transition: { duration: 0.5, ease: 'easeOut' }
    }
  }

  return (
    <div className="chat-welcome" role="presentation">
      {/* Float wrapper */}
      <motion.div
        animate={{ y: [0, -3, 0] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        style={{ display: 'flex' }}
      >
        <motion.img
          layoutId="axiom-hero-logo"
          src={theme === 'dark' ? LogoDark : LogoLight}
          alt="Axiom Logo"
          initial={{ rotate: -360, scale: 0.8 }}
          animate={{ rotate: 0, scale: 1 }}
          transition={{ 
            rotate: { duration: 2.8, ease: [0.16, 1, 0.3, 1] },
            scale: { duration: 0.8, ease: 'easeOut' },
            layout: { duration: 1.5, ease: [0.16, 1, 0.3, 1] }
          }}
          onHoverStart={() => {
            if (isSpinning.current) return
            spinControls.start({
              scale: 1.05,
              rotate: [0, -4, 4, -2, 2, 0],
              transition: { duration: 1.2, ease: 'easeInOut' }
            })
          }}
          onHoverEnd={() => {
            if (isSpinning.current) return
            spinControls.start({
              scale: 1,
              rotate: 0,
              transition: { duration: 0.6, ease: 'easeOut' }
            })
          }}
          onClick={handleClick}
          style={{ width: '160px', height: 'auto', cursor: 'pointer', filter: 'drop-shadow(0 8px 24px rgba(0,0,0,0.15))' }}
        />
      </motion.div>
      <motion.h2
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '8px' }}
      >
        {words.map((word, i) => (
          <motion.span key={i} variants={wordVariants} style={{ display: 'inline-block' }}>
            {word}
          </motion.span>
        ))}
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
      >
        Ask anything. Axiom routes your query through a semantic cache and
        model cascade to minimize token cost automatically.
      </motion.p>
    </div>
  )
}

