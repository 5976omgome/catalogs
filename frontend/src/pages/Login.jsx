import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './Login.css'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-bg" />
      <div className="login-card">
        <div className="login-logo">
          <img src="/logos/ignite.svg" alt="IGNITE" />
          <h1>VIRTUAL SCOUT</h1>
          <p>Catalog Scouting System</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label htmlFor="email">Username</label>
            <input
              id="email"
              type="text"
              autoComplete="username"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="admin"
              required
              autoFocus
            />
          </div>
          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
              required
            />
          </div>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" className="login-submit" disabled={loading}>
            {loading ? 'Signing in...' : 'SIGN IN'}
          </button>
        </form>
        <div className="login-footer">
          <span>IGNITE THE LABEL &middot; Q2 2026</span>
        </div>
      </div>
    </div>
  )
}
