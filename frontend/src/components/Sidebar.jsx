import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, Users, BarChart3, Zap, ChevronLeft, ChevronRight, LogOut } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import './Sidebar.css'

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const [clock, setClock] = useState('')
  const { logout, user } = useAuth()
  const location = useLocation()

  useEffect(() => {
    function tick() {
      setClock(new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  // Update page title based on route
  useEffect(() => {
    const titles = {
      '/dashboard': 'IGNITE: DASHBOARD',
      '/settings': 'IGNITE: SETTINGS',
      '/artists': 'IGNITE: ARTISTS',
      '/tools/chartporter': 'IGNITE: CHARTPORTER',
      '/tools/genitractor': 'IGNITE: GENITRACTOR',
    }
    document.title = titles[location.pathname] || 'IGNITE: VIRTUAL SCOUT'
  }, [location.pathname])

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Brand */}
      <div className="sb-brand">
        <div className="sb-logo">
          <img src="/logos/ignite.svg" alt="IGNITE" className="sb-logo-img" />
        </div>
        {!collapsed && (
          <div className="sb-brand-text">
            <span className="sb-title">Virtual Scout</span>
            <span className="sb-subtitle">Contact Extraction</span>
          </div>
        )}
        {!collapsed && <span className="sb-clock">{clock}</span>}
      </div>

      {/* Nav */}
      <nav className="sb-nav">
        <NavLink to="/dashboard" className="sb-item" title="Dashboard">
          <LayoutDashboard size={18} />
          {!collapsed && <span>Dashboard</span>}
        </NavLink>
        <NavLink to="/settings" className="sb-item" title="Settings">
          <Settings size={18} />
          {!collapsed && <span>Settings</span>}
        </NavLink>

        <div className="sb-divider">
          {!collapsed && <span className="sb-section">LIBRARY</span>}
        </div>
        <NavLink to="/artists" className="sb-item" title="Artists">
          <Users size={18} />
          {!collapsed && <span>Artists</span>}
        </NavLink>

        <div className="sb-divider">
          {!collapsed && <span className="sb-section">TOOLS</span>}
        </div>
        <NavLink to="/tools/chartporter" className="sb-item" title="Chartporter">
          <BarChart3 size={18} />
          {!collapsed && <span>Chartporter</span>}
        </NavLink>
        <NavLink to="/tools/genitractor" className="sb-item" title="Genitractor">
          <Zap size={18} />
          {!collapsed && <span>Genitractor</span>}
        </NavLink>
      </nav>

      {/* Footer */}
      <div className="sb-footer">
        <button className="sb-item sb-logout" onClick={logout} title="Log out">
          <LogOut size={18} />
          {!collapsed && <span>Log Out</span>}
        </button>
        <button className="sb-toggle" onClick={() => setCollapsed(!collapsed)} title={collapsed ? 'Expand' : 'Collapse'}>
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
  )
}
