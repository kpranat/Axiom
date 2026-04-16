import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import LogoLight from '../assets/LogoLight.png'

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

export default function AuthPage() {
  const navigate = useNavigate()
  const { login, signup, isAuthenticated, isInitializing } = useAuth()

  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isInitializing && isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, isInitializing, navigate])

  const content = useMemo(() => {
    if (mode === 'login') {
      return {
        title: 'Welcome back',
        subtitle: 'Sign in to continue to Axiom',
        submitLabel: 'Sign in',
        footerText: "Don't have an account?",
        footerAction: 'Sign up',
      }
    }

    return {
      title: 'Create your account',
      subtitle: 'Start using Axiom in minutes',
      submitLabel: 'Create account',
      footerText: 'Already have an account?',
      footerAction: 'Login',
    }
  }, [mode])

  async function handleSubmit(e) {
    e.preventDefault()
    if (loading) {
      return
    }

    setError('')

    if (!isValidEmail(email.trim())) {
      setError('Please enter a valid email')
      return
    }
    if (password.trim().length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    if (mode === 'signup') {
      if (!name.trim()) {
        setError('Please enter your name')
        return
      }
      if (password !== confirmPassword) {
        setError("Passwords don't match")
        return
      }
    }

    setLoading(true)
    try {
      if (mode === 'login') {
        await login(email.trim(), password)
      } else {
        await signup(name.trim(), email.trim(), password)
      }
      navigate('/', { replace: true })
    } catch (err) {
      setError(err?.message || 'Something went wrong, please try again')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page" aria-label="Authentication">
      <motion.div
        className="auth-blob auth-blob-a"
        animate={{
          x: [0, 24, -18, 0],
          y: [0, -16, 10, 0],
          scale: [1, 1.08, 0.96, 1],
        }}
        transition={{ duration: 14, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="auth-blob auth-blob-b"
        animate={{
          x: [0, -18, 22, 0],
          y: [0, 14, -10, 0],
          scale: [1, 0.95, 1.06, 1],
        }}
        transition={{ duration: 16, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="auth-blob auth-blob-c"
        animate={{
          x: [0, -22, 14, 0],
          y: [0, 10, -14, 0],
          scale: [1, 1.05, 0.94, 1],
        }}
        transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }}
      />

      <div className="auth-grain" aria-hidden="true" />

      <section className="auth-shell">
        <motion.div
          className="auth-brand"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.05, ease: 'easeOut' }}
        >
          <img src={LogoLight} alt="Axiom" className="auth-logo" />
        </motion.div>

        <motion.h1
          className="auth-title"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15, ease: 'easeOut' }}
        >
          {content.title}
        </motion.h1>

        <motion.p
          className="auth-subtext"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.25, ease: 'easeOut' }}
        >
          {content.subtitle}
        </motion.p>

        <motion.div
          className="auth-tabs"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.35, ease: 'easeOut' }}
        >
          <button
            type="button"
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => {
              setMode('login')
              setError('')
            }}
          >
            Login
          </button>
          <button
            type="button"
            className={`auth-tab ${mode === 'signup' ? 'active' : ''}`}
            onClick={() => {
              setMode('signup')
              setError('')
            }}
          >
            Sign up
          </button>
        </motion.div>

        <AnimatePresence mode="wait">
          <motion.form
            key={mode}
            className="auth-form"
            onSubmit={handleSubmit}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.24, ease: 'easeOut' }}
          >
            {mode === 'signup' && (
              <motion.input
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.32, delay: 0.45, ease: 'easeOut' }}
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Name"
                className="auth-input"
                autoComplete="name"
              />
            )}

            <motion.input
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, delay: mode === 'signup' ? 0.55 : 0.45, ease: 'easeOut' }}
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="Email"
              type="email"
              className="auth-input"
              autoComplete="email"
            />

            <motion.input
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, delay: mode === 'signup' ? 0.65 : 0.55, ease: 'easeOut' }}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              type="password"
              className="auth-input"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />

            {mode === 'signup' && (
              <motion.input
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.32, delay: 0.75, ease: 'easeOut' }}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="Confirm password"
                type="password"
                className="auth-input"
                autoComplete="new-password"
              />
            )}

            {mode === 'login' && (
              <motion.a
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.32, delay: 0.65, ease: 'easeOut' }}
                href="#"
                className="auth-forgot"
                onClick={e => e.preventDefault()}
              >
                Forgot password?
              </motion.a>
            )}

            <AnimatePresence>
              {error && (
                <motion.div
                  key={error}
                  className="auth-error"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: [0, -4, 4, -2, 2, 0] }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.34, ease: 'easeOut' }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <motion.button
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, delay: mode === 'signup' ? 0.85 : 0.75, ease: 'easeOut' }}
              type="submit"
              disabled={loading}
              className="auth-submit"
            >
              {loading ? (
                <span className="auth-loading">
                  <motion.span
                    className="auth-spinner"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                  />
                  Loading
                </span>
              ) : (
                content.submitLabel
              )}
            </motion.button>
          </motion.form>
        </AnimatePresence>

        <motion.p
          className="auth-footer"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.95, ease: 'easeOut' }}
        >
          {content.footerText}{' '}
          <button
            type="button"
            className="auth-footer-link"
            onClick={() => {
              setMode(prev => (prev === 'login' ? 'signup' : 'login'))
              setError('')
            }}
          >
            {content.footerAction}
          </button>
        </motion.p>
      </section>
    </main>
  )
}
