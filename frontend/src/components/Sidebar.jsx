import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, Users, BarChart3, Zap, ChevronLeft, ChevronRight, LogOut } from 'lucide-react'
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

const TOOLTIPS = {
  chartporter: 'Audits artist catalogs for ownership conflicts by cross-referencing iTunes and Deezer label data against known major-label and third-party distributors.',
  genitact: 'Extracts Instagram and Facebook contacts from Genius artist profiles using balanced name-matching with confidence scoring.',
}

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const [clock, setClock] = useState('')
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

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Brand */}
      <div className="sb-brand">
        <img src="/logos/ignite.svg" alt="IGNITE" className="sb-logo-img" />
        {!collapsed && (
          <>
            <div className="sb-brand-text">
              <span className="sb-title">VIRTUAL SCOUT</span>
              <span className="sb-subtitle">{subtitle}</span>
            </div>
            <span className="sb-clock">{clock}</span>
          </>
        )}
      </div>

      {/* Nav */}
      <nav className="sb-nav">
        <NavLink to="/dashboard" className="sb-item">
          <LayoutDashboard size={16} />
          {!collapsed && <span>Dashboard</span>}
        </NavLink>
        <NavLink to="/settings" className="sb-item">
          <Settings size={16} />
          {!collapsed && <span>Settings</span>}
        </NavLink>

        <div className="sb-divider">
          {!collapsed && <span className="sb-section">Library</span>}
        </div>
        <NavLink to="/artists" className="sb-item">
          <Users size={16} />
          {!collapsed && <span>Artists</span>}
        </NavLink>

        <div className="sb-divider">
          {!collapsed && <span className="sb-section">Tools</span>}
        </div>
        <div className="sb-item-wrap">
          <NavLink to="/tools/chartporter" className="sb-item">
            <BarChart3 size={16} />
            {!collapsed && <span>Chartporter</span>}
          </NavLink>
          {!collapsed && <div className="sb-tooltip">{TOOLTIPS.chartporter}</div>}
        </div>
        <div className="sb-item-wrap">
          <NavLink to="/tools/genitact" className="sb-item">
            <Zap size={16} />
            {!collapsed && <span>Genitact</span>}
          </NavLink>
          {!collapsed && <div className="sb-tooltip">{TOOLTIPS.genitact}</div>}
        </div>
      </nav>

      {/* Footer */}
      <div className="sb-footer">
        <button className="sb-item sb-logout" onClick={logout}>
          <LogOut size={16} />
          {!collapsed && <span>Log Out</span>}
        </button>
        <button className="sb-toggle" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </aside>
  )
}
