import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, Users, BarChart3, Zap, LogOut } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import './Sidebar.css'

const SUBTITLES = {
  '/dashboard': 'CATALOG SCOUTING',
  '/settings': 'CONFIGURATION',
  '/artists': 'ARTIST LIBRARY',
  '/tools/chartporter': 'CATALOG INTELLIGENCE',
  '/tools/genitact': 'CONTACT EXTRACTION',
}

const TITLES = {
  '/dashboard': 'IGNITE: DASHBOARD',
  '/settings': 'IGNITE: SETTINGS',
  '/artists': 'IGNITE: ARTISTS',
  '/tools/chartporter': 'IGNITE: CHARTPORTER',
  '/tools/genitact': 'IGNITE: GENITACT',
}

const TOOLS = [
  { to: '/tools/chartporter', icon: BarChart3, label: 'Chartporter', tip: 'Audits artist catalogs for ownership conflicts by cross-referencing iTunes and Deezer label data.' },
  { to: '/tools/genitact', icon: Zap, label: 'Genitact', tip: 'Extracts Instagram and Facebook contacts from Genius artist profiles using balanced name-matching.' },
]

export default function Sidebar() {
  const [hovered, setHovered] = useState(false)
  const [clock, setClock] = useState('')
  const [tip, setTip] = useState(null)
  const { logout } = useAuth()
  const location = useLocation()

  useEffect(() => {
    function tick() {
      setClock(new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    document.title = TITLES[location.pathname] || 'IGNITE: VIRTUAL SCOUT'
  }, [location.pathname])

  const subtitle = SUBTITLES[location.pathname] || 'CATALOG SCOUTING'
  const expanded = hovered

  return (
    <aside
      className={`sidebar ${expanded ? 'expanded' : 'collapsed'}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setTip(null) }}
    >
      {/* Brand */}
      <div className="sb-brand">
        <img src="/logos/ignite.svg" alt="IGNITE" className="sb-logo-img" />
        <div className="sb-brand-content">
          <div className="sb-brand-row">
            <span className="sb-title">VIRTUAL SCOUT</span>
            <span className="sb-clock">{clock}</span>
          </div>
          <span className="sb-subtitle">{subtitle}</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="sb-nav">
        <NavLink to="/dashboard" className="sb-item">
          <LayoutDashboard size={16} />
          <span className="sb-label">Dashboard</span>
        </NavLink>
        <NavLink to="/settings" className="sb-item">
          <Settings size={16} />
          <span className="sb-label">Settings</span>
        </NavLink>

        <div className="sb-divider">
          <span className="sb-section">Library</span>
        </div>
        <NavLink to="/artists" className="sb-item">
          <Users size={16} />
          <span className="sb-label">Artists</span>
        </NavLink>

        <div className="sb-divider">
          <span className="sb-section">Tools</span>
        </div>
        {TOOLS.map(({ to, icon: Icon, label, tip: text }) => (
          <NavLink
            key={to}
            to={to}
            className="sb-item"
            onMouseEnter={e => {
              const r = e.currentTarget.getBoundingClientRect()
              setTip({ text, top: r.top + r.height / 2, left: r.right + 10 })
            }}
            onMouseLeave={() => setTip(null)}
          >
            <Icon size={16} />
            <span className="sb-label">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sb-footer">
        <button className="sb-item sb-logout" onClick={logout}>
          <LogOut size={16} />
          <span className="sb-label">Log Out</span>
        </button>
        <div className="sb-version">
          <span className="sb-version-dot" />
          <span className="sb-version-label">VERSION 6.0</span>
        </div>
      </div>

      {/* Floating tooltip — fixed position so it never clips or shifts layout */}
      {tip && (
        <div className="sb-tooltip" style={{ top: tip.top, left: tip.left }}>
          {tip.text}
        </div>
      )}
    </aside>
  )
}
