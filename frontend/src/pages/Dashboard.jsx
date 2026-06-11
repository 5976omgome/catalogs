import { useState, useEffect } from 'react'
import { Users, Percent, Mail, TrendingUp } from 'lucide-react'
import './Dashboard.css'

export default function Dashboard() {
  const [stats, setStats] = useState({ total_processed: 0, total_yield: 0, emails_sent: 0, batches: 0, moving_forward: 0, not_sent: 0 })

  useEffect(() => {
    fetch('/api/stats/lifetime')
      .then(r => r.ok ? r.json() : {})
      .then(d => setStats(s => ({ ...s, ...d })))
      .catch(() => {})
  }, [])

  return (
    <div className="dashboard">
      <div className="dash-widgets">
        <Widget icon={<Users size={18} />} label="Total Artists" value={stats.total_processed.toLocaleString()} color="var(--accent)" />
        <Widget icon={<Percent size={18} />} label="Yield Rate" value={`${stats.total_yield}%`} sub={`${stats.emails_sent} / ${stats.total_processed}`} color="var(--frost)" />
        <Widget icon={<Mail size={18} />} label="Emails Sent" value={stats.emails_sent.toLocaleString()} sub={`${stats.not_sent} remaining`} color="var(--peach)" />
        <Widget icon={<TrendingUp size={18} />} label="Moving Forward" value={stats.moving_forward.toLocaleString()} sub={`${stats.batches} weeks`} color="var(--green)" />
      </div>

      <div className="dash-mission">
        <div className="dash-mission-header">
          <h2>IGNITE THE LABEL</h2>
          <p className="dash-tagline">MGMT &middot; CATALOG &middot; PUBLISHING &middot; LABEL</p>
        </div>
        <div className="dash-mission-body">
          <section>
            <h3>Platform Purpose</h3>
            <p>Find artists that own their catalog, fit what we're looking for, have contact information, have a reason to take a deal, and make it to outreach.</p>
          </section>
          <section>
            <h3>Daily Process</h3>
            <ul>
              <li>Start with a Chartmetric export (250K–2M monthly listeners)</li>
              <li>Run Chartporter — audit ownership via iTunes/Deezer labels</li>
              <li>Run Genitact — pull Instagram/Facebook contacts via Genius</li>
              <li>Manually review → qualify → outreach</li>
            </ul>
            <p className="dash-goal">Goal: 100 artists reviewed/day &middot; ~20 qualified opportunities found/day</p>
          </section>
          <section>
            <h3>Priorities</h3>
            <ol>
              <li><strong>Licensing Opportunities</strong> — always the priority</li>
              <li><strong>Buyout Opportunities</strong> — larger catalogs, stable revenue</li>
              <li><strong>A&R Opportunities</strong> — developing artists worth signing</li>
            </ol>
          </section>
        </div>
      </div>
    </div>
  )
}

function Widget({ icon, label, value, sub, color }) {
  return (
    <div className="widget" style={{ '--widget-color': color }}>
      <div className="widget-icon">{icon}</div>
      <div className="widget-data">
        <span className="widget-value">{value}</span>
        <span className="widget-label">{label}</span>
        {sub && <span className="widget-sub">{sub}</span>}
      </div>
    </div>
  )
}
