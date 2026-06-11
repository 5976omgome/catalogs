import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import './Shell.css'

const ROUTE_THEMES = {
  '/dashboard': 'theme-dashboard',
  '/settings': 'theme-settings',
  '/artists': 'theme-artists',
  '/tools/chartporter': 'theme-chartporter',
  '/tools/genitact': 'theme-genitract',
  '/tools/drafter': 'theme-drafter',
  '/tools/followup': 'theme-followup',
}

export default function Shell() {
  const location = useLocation()
  const theme = ROUTE_THEMES[location.pathname] || 'theme-dashboard'

  return (
    <div className={`shell ${theme}`}>
      <Sidebar />
      <main className="shell-content">
        <Outlet />
      </main>
    </div>
  )
}
