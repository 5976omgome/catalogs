import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Artists from './pages/Artists'
import Shell from './components/Shell'

function ProtectedRoute({ children, title }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading-screen">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  document.title = title || 'IGNITE: VIRTUAL SCOUT'
  return children
}

function AppRoutes() {
  const { user, loading } = useAuth()

  if (loading) return <div className="loading-screen">Loading...</div>

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/" element={<ProtectedRoute title="IGNITE: DASHBOARD"><Shell /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="settings" element={<Settings />} />
        <Route path="artists" element={<Artists />} />
        <Route path="tools/chartporter" element={<div className="tool-placeholder">Chartporter (Phase 3)</div>} />
        <Route path="tools/genitractor" element={<div className="tool-placeholder">Genitractor (Phase 3)</div>} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
