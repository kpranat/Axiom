import { Navigate } from 'react-router-dom'
import { jwtDecode } from 'jwt-decode'
import { useEffect } from 'react'
import { useAuth } from '../context/AuthContext.jsx'

function isTokenExpired(token) {
  if (!token) {
    return true
  }

  try {
    const decoded = jwtDecode(token)
    if (!decoded?.exp) {
      return true
    }
    return decoded.exp * 1000 <= Date.now()
  } catch {
    return true
  }
}

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, token, logout, isInitializing } = useAuth()
  const tokenExpired = isAuthenticated && isTokenExpired(token)

  useEffect(() => {
    if (tokenExpired) {
      logout()
    }
  }, [tokenExpired, logout])

  if (isInitializing) {
    return null
  }

  if (!isAuthenticated || tokenExpired) {
    return <Navigate to="/login" replace />
  }

  return children
}
