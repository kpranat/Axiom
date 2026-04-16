/**
 * Message.jsx — Single message bubble with model/cache badge.
 * Per PRD: each message shows badge for cache, small model, or large model.
 */

import { motion } from 'framer-motion'

export default function Message({ message, onAnimationComplete }) {
  const isUser = message.role === 'user'
  const content = normalizeContent(message.content)

  const badgeInfo = getBadge(message)
  const timeStr = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  const renderAiContent = () => {
    const segments = splitByCodeFence(content)

    return (
      <motion.div
        className="message-content"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
        onAnimationComplete={onAnimationComplete}
      >
        {segments.map((segment, index) => {
          if (segment.type === 'code') {
            return (
              <pre key={index} className="message-code">
                <code>{segment.value}</code>
              </pre>
            )
          }

          return (
            <p key={index} className="message-text">
              {segment.value}
            </p>
          )
        })}
      </motion.div>
    )
  }

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'ai'}`}>
      <div className="message-bubble">
        {isUser ? content : renderAiContent()}
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

function normalizeContent(value) {
  if (typeof value === 'string') {
    return value
  }
  if (value == null) {
    return ''
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function splitByCodeFence(content) {
  const result = []
  const regex = /```(?:[a-zA-Z0-9_+-]+)?\n?([\s\S]*?)```/g
  let cursor = 0
  let match = regex.exec(content)

  while (match) {
    const codeStart = match.index
    const codeEnd = regex.lastIndex

    if (codeStart > cursor) {
      const textChunk = content.slice(cursor, codeStart)
      if (textChunk.trim() !== '') {
        result.push({ type: 'text', value: textChunk })
      }
    }

    result.push({ type: 'code', value: match[1].replace(/\n$/, '') })
    cursor = codeEnd
    match = regex.exec(content)
  }

  if (cursor < content.length) {
    const trailingText = content.slice(cursor)
    if (trailingText.trim() !== '') {
      result.push({ type: 'text', value: trailingText })
    }
  }

  if (result.length === 0) {
    return [{ type: 'text', value: content }]
  }

  return result
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
