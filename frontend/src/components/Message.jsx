/**
 * Message.jsx — Single message bubble with model/cache badge.
 * Per PRD: each message shows badge for cache, small model, or large model.
 */

export default function Message({ message }) {
  const isUser = message.role === 'user'

  const badgeInfo = getBadge(message)
  const timeStr = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'ai'}`}>
      <div className="message-bubble">{message.content}</div>

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
