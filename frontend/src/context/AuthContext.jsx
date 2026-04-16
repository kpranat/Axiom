import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { jwtDecode } from 'jwt-decode'
import { api, clearStoredToken, getStoredToken, setStoredToken } from '../lib/api.js'

const USER_KEY = 'axiom_user'

const AuthContext = createContext(null)

function decodeToken(token) {
  try {
    return jwtDecode(token)
  } catch {
    return null
  }
}

function isTokenExpired(decoded) {
  if (!decoded?.exp) {
    return true
  }
  return decoded.exp * 1000 <= Date.now()
}

function userFromDecodedToken(decoded, fallback = null) {
  if (!decoded) {
    return fallback
  }

  return {
    id: decoded.user_id || fallback?.id || '',
    email: decoded.email || fallback?.email || '',
    plan: decoded.plan || fallback?.plan || 'free',
    created_at: fallback?.created_at || null,
    updated_at: fallback?.updated_at || null,
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isInitializing, setIsInitializing] = useState(true)

  const clearAuthState = useCallback(() => {
    clearStoredToken()
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
    setIsAuthenticated(false)
  }, [])

  const persistAuthState = useCallback((nextToken, nextUser) => {
    setStoredToken(nextToken)
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
    setToken(nextToken)
    setUser(nextUser)
    setIsAuthenticated(true)
  }, [])

  useEffect(() => {
    let mounted = true

    function readCachedUser() {
      const rawUser = localStorage.getItem(USER_KEY)
      if (!rawUser) {
        return null
      }

      try {
        return JSON.parse(rawUser)
      } catch {
        return null
      }
    }

    async function refreshCurrentUser(storedToken) {
      try {
        const me = await api.me()
        if (mounted && me?.user) {
          persistAuthState(storedToken, me.user)
        }
      } catch (err) {
        if (err?.status === 401 && mounted) {
          clearAuthState()
        }
      }
    }

    function restore() {
      const storedToken = getStoredToken()
      if (!storedToken) {
        if (mounted) {
          setIsInitializing(false)
        }
        return
      }

      const decoded = decodeToken(storedToken)
      if (!decoded || isTokenExpired(decoded)) {
        clearAuthState()
        if (mounted) {
          setIsInitializing(false)
        }
        return
      }

      const cachedUser = readCachedUser()

      const optimisticUser = userFromDecodedToken(decoded, cachedUser)
      if (mounted) {
        setToken(storedToken)
        setUser(optimisticUser)
        setIsAuthenticated(true)
        setIsInitializing(false)
      }

      // Refresh user details in background so reload is instant.
      void refreshCurrentUser(storedToken)
    }

    restore()

    return () => {
      mounted = false
    }
  }, [clearAuthState, persistAuthState])

  const login = useCallback(async (email, password) => {
    const data = await api.login(email, password)
    persistAuthState(data.token, data.user)
    return data
  }, [persistAuthState])

  const signup = useCallback(async (name, email, password) => {
    const data = await api.signup(name, email, password)
    persistAuthState(data.token, data.user)
    return data
  }, [persistAuthState])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // Stateless JWT mode: client-side token deletion remains authoritative.
    }
    clearAuthState()
  }, [clearAuthState])

  const value = useMemo(() => ({
    user,
    token,
    login,
    signup,
    logout,
    isAuthenticated,
    isInitializing,
  }), [user, token, login, signup, logout, isAuthenticated, isInitializing])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
