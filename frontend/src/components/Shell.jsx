import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import './Shell.css'

export default function Shell() {
  return (
    <div className="shell">
      <Sidebar />
      <main className="shell-content">
        <Outlet />
      </main>
    </div>
  )
}
