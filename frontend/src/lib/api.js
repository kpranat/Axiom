const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'
const TOKEN_KEY = 'axiom_token'

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export const authFetch = async (endpoint, options = {}) => {
  const token = getStoredToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }

  return fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })
}

async function parseResponse(response) {
  const raw = await response.text()
  if (!raw) {
    return null
  }

  try {
    return JSON.parse(raw)
  } catch {
    return { message: raw }
  }
}

function toMessage(status, payload) {
  const code = payload?.error

  if (status === 401 && code === 'token_expired') {
    return 'Session expired'
  }
  if (status === 401) {
    return 'Invalid email or password'
  }
  if (status === 409) {
    return 'An account with this email already exists'
  }
  if (status >= 500) {
    return 'Something went wrong, please try again'
  }

  return payload?.error || payload?.message || `HTTP ${status}`
}

export async function requestJSON(endpoint, options = {}) {
  const response = await authFetch(endpoint, options)
  const payload = await parseResponse(response)

  if (!response.ok) {
    const err = new Error(toMessage(response.status, payload))
    err.status = response.status
    err.code = payload?.error || null
    err.payload = payload
    throw err
  }

  return payload
}

export const api = {
  login: (email, password) => requestJSON('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  }),
  signup: (name, email, password) => requestJSON('/api/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ name, email, password }),
  }),
  me: () => requestJSON('/api/auth/me', { method: 'GET' }),
  logout: () => requestJSON('/api/auth/logout', { method: 'POST' }),
}
