/**
 * Message.jsx — Single message bubble with model/cache badge.
 * Per PRD: each message shows badge for cache, small model, or large model.
 */

import { motion } from 'framer-motion'

export default function Message({ message }) {
  const isUser = message.role === 'user'

  const badgeInfo = getBadge(message)
  const timeStr = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  const renderAiContent = () => {
    const words = message.content.split(' ')

    return (
      <motion.div
        variants={{
          hidden: { opacity: 1 },
          visible: {
            opacity: 1,
            transition: { staggerChildren: 0.08 }
          }
        }}
        initial="hidden"
        animate="visible"
        style={{ display: 'inline-block' }}
      >
        {words.map((word, i) => (
          <motion.span
            key={i}
            variants={{
              hidden: { opacity: 0, y: 4 },
              visible: { 
                opacity: 1, 
                y: 0, 
                transition: { duration: 0.3, ease: 'easeOut' }
              }
            }}
            style={{ display: 'inline-block', whiteSpace: 'pre-wrap' }}
          >
            {word + (i < words.length - 1 ? ' ' : '')}
          </motion.span>
        ))}
      </motion.div>
    )
  }

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'ai'}`}>
      <div className="message-bubble">
        {isUser ? message.content : renderAiContent()}
      </div>

      {!isUser && (
        <div className="message-meta">
          {badgeInfo && (
            <span className={`badge badge-${badgeInfo.type}`} aria-label={badgeInfo.label}>
              {badgeInfo.icon} {badgeInfo.label}
            </span>
          )}
          {timeStr && <span className="message-time">{timeStr}</span>}
        </div>
      )}
    </div>
  )
}

function getBadge(message) {
  if (message.cache_hit) {
    return { type: 'cache', label: 'Cache Hit', icon: '⚡' }
  }
  if (message.model_used === 'gpt-4o') {
    return { type: 'large', label: 'GPT-4o', icon: '🔮' }
  }
  if (message.model_used === 'gpt-3.5-turbo') {
    return { type: 'small', label: 'GPT-3.5', icon: '✦' }
  }
  return null
}
