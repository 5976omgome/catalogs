import { useState, useEffect } from 'react'
import { BarChart3, Percent, Mail, Activity } from 'lucide-react'
import './Dashboard.css'

export default function Dashboard() {
  const [stats, setStats] = useState({ total_processed: 0, total_yield: 0, emails_sent: 0, api_usage: null })

  useEffect(() => {
    fetch('/api/stats/lifetime')
      .then(r => r.ok ? r.json() : {})
      .then(d => setStats(s => ({ ...s, ...d })))
      .catch(() => {})
  }, [])

  return (
    <div className="dashboard">
      {/* Widget Row */}
      <div className="dash-widgets">
        <Widget icon={<BarChart3 size={20} />} label="Total Processed" value={stats.total_processed.toLocaleString()} color="var(--dash-cta)" />
        <Widget icon={<Percent size={20} />} label="Total % Yield" value={`${stats.total_yield}%`} color="var(--dash-highlight)" />
        <Widget icon={<Mail size={20} />} label="Emails Sent" value={stats.emails_sent.toLocaleString()} color="var(--dash-accent)" />
        <Widget icon={<Activity size={20} />} label="API Status" value={stats.api_usage || 'Healthy'} color="var(--success)" />
      </div>

      {/* Mission Content */}
      <div className="dash-mission">
        <div className="dash-mission-header">
          <h2>IGNITE THE LABEL</h2>
          <p className="dash-tagline">MGMT &middot; CATALOG &middot; PUBLISHING &middot; LABEL</p>
        </div>
        <div className="dash-mission-body">
          <section>
            <h3>Platform Purpose</h3>
            <p>
              The goal isn't just to find artists. The goal is to find artists that actually make sense for IGNITE to talk to.
              Artists that own their catalog, fit what we're looking for, have contact information available, have a reason to take a deal, and make it to outreach.
            </p>
          </section>
          <section>
            <h3>Daily Process</h3>
            <ul>
              <li>Start with a Chartmetric export (250K–2M monthly listeners)</li>
              <li>Run Chartporter — audit ownership via iTunes/Deezer labels</li>
              <li>Run Genitractor — pull Instagram/Facebook contacts via Genius</li>
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

function Widget({ icon, label, value, color }) {
  return (
    <div className="widget" style={{ '--widget-color': color }}>
      <div className="widget-icon">{icon}</div>
      <div className="widget-data">
        <span className="widget-value">{value}</span>
        <span className="widget-label">{label}</span>
      </div>
    </div>
  )
}
