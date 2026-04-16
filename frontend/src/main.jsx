import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import AuthPage from './pages/AuthPage.jsx'
import './index.css'

function LoginRoute() {
  const { isAuthenticated, isInitializing } = useAuth()
  if (isInitializing) {
    return null
  }
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }
  return <AuthPage />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={(
              <ProtectedRoute>
                <App />
              </ProtectedRoute>
            )}
          />
          <Route path="/login" element={<LoginRoute />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
)
