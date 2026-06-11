import { useState, useEffect } from 'react'
import { Key, Check, X, Mail, Globe, Shield, Zap } from 'lucide-react'
import './Settings.css'

export default function Settings() {
  const [keys, setKeys] = useState({})
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState({})
  const [gmailStatus, setGmailStatus] = useState(null)

  useEffect(() => {
    fetch('/api/settings/keys').then(r => r.ok ? r.json() : { keys: {} }).then(d => setKeys(d.keys || {})).catch(() => {})
    fetch('/api/drafter/auth-check').then(r => r.json()).then(d => setGmailStatus(d)).catch(() => {})
  }, [])

  async function saveKey(slotId, service, slot) {
    const val = values[slotId]
    if (!val || !val.trim()) return
    setSaving(s => ({ ...s, [slotId]: 'saving' }))
    try {
      const r = await fetch('/api/settings/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ service, slot, key: val.trim() }) })
      const d = await r.json()
      if (r.ok) { setSaving(s => ({ ...s, [slotId]: d.valid ? 'valid' : 'invalid' })); setKeys(k => ({ ...k, [slotId]: { set: true, valid: d.valid, masked: d.masked } })); setValues(v => ({ ...v, [slotId]: '' })) }
      else setSaving(s => ({ ...s, [slotId]: 'error' }))
    } catch { setSaving(s => ({ ...s, [slotId]: 'error' })) }
    setTimeout(() => setSaving(s => ({ ...s, [slotId]: null })), 2500)
  }

  function KeySlot({ id, label, service, slot }) {
    return (
      <div className="key-slot">
        <div className="key-slot-header">
          <label>{label}</label>
          <span className={`key-dot ${keys[id]?.valid ? 'ok' : keys[id]?.set ? 'bad' : ''}`} />
        </div>
        <div className="key-input-row">
          <input type="password" placeholder={keys[id]?.masked || 'Paste key...'} value={values[id] || ''} onChange={e => setValues(v => ({ ...v, [id]: e.target.value }))} onKeyDown={e => e.key === 'Enter' && saveKey(id, service, slot)} />
          <button className="key-save" onClick={() => saveKey(id, service, slot)}>{saving[id] === 'saving' ? '...' : 'SAVE'}</button>
        </div>
      </div>
    )
  }

  return (
    <div className="settings">
      {/* Header */}
      <div className="settings-header">
        <h1>CONFIGURATION</h1>
      </div>

      {/* Connection Status */}
      <section className="settings-section">
        <h2><Globe size={13} /> Connections</h2>
        <div className="conn-grid">
          <div className="conn-item">
            <span className={`conn-dot ${gmailStatus?.ready ? 'ok' : ''}`} />
            <div className="conn-info">
              <span className="conn-name">Gmail API</span>
              <span className="conn-detail">{gmailStatus?.ready ? 'gavin@ignitethelabel.com' : 'Not connected'}</span>
            </div>
            <button className="conn-btn" onClick={async () => { try { await fetch('/api/drafter/authorize', { method: 'POST' }); setGmailStatus({ ready: true }); } catch (e) { alert(e.message) } }}>
              {gmailStatus?.ready ? 'CONNECTED' : 'CONNECT'}
            </button>
          </div>
          <div className="conn-item">
            <span className="conn-dot ok" />
            <div className="conn-info">
              <span className="conn-name">iTunes</span>
              <span className="conn-detail">No key required</span>
            </div>
            <span className="conn-ok"><Check size={12} /></span>
          </div>
          <div className="conn-item">
            <span className="conn-dot ok" />
            <div className="conn-info">
              <span className="conn-name">Deezer</span>
              <span className="conn-detail">No key required</span>
            </div>
            <span className="conn-ok"><Check size={12} /></span>
          </div>
        </div>
      </section>

      {/* Genius Keys (Genitact) */}
      <section className="settings-section">
        <h2><Zap size={13} /> Genius API Keys <span className="section-badge">Genitact</span></h2>
        <p className="settings-hint">4 key slots — auto-rotates to the next key when one is rate-limited.</p>
        <div className="key-grid">
          <KeySlot id="genius_1" label="Slot 1" service="genius" slot={1} />
          <KeySlot id="genius_2" label="Slot 2" service="genius" slot={2} />
          <KeySlot id="genius_3" label="Slot 3" service="genius" slot={3} />
          <KeySlot id="genius_4" label="Slot 4" service="genius" slot={4} />
        </div>
      </section>

      {/* AI Keys (Chartport) */}
      <section className="settings-section">
        <h2><Key size={13} /> AI Keys <span className="section-badge">Chartport</span></h2>
        <p className="settings-hint">Used for catalog ownership analysis and AI-assisted classification.</p>
        <div className="key-grid">
          <KeySlot id="groq" label="Groq" service="groq" slot={1} />
          <KeySlot id="gemini" label="Gemini" service="gemini" slot={1} />
        </div>
      </section>

      {/* Outreach */}
      <section className="settings-section">
        <h2><Mail size={13} /> Outreach</h2>
        <div className="pref-grid">
          <div className="pref-item">
            <label>Scouting Email 1</label>
            <input type="email" defaultValue="gavin@ignitethelabel.com" readOnly style={{ opacity: .7 }} />
          </div>
          <div className="pref-item">
            <label>Scouting Email 2</label>
            <input type="email" defaultValue="gavin.roy07@ignitethelabel.com" readOnly style={{ opacity: .7 }} />
          </div>
        </div>
      </section>

      {/* System */}
      <section className="settings-section">
        <h2><Shield size={13} /> System</h2>
        <div className="pref-grid">
          <div className="pref-item">
            <label>Timezone</label>
            <input type="text" value={Intl.DateTimeFormat().resolvedOptions().timeZone} readOnly style={{ opacity: .7 }} />
          </div>
          <div className="pref-item">
            <label>Storage</label>
            <input type="text" value="Local (~/Documents/catalogs/data/)" readOnly style={{ opacity: .7 }} />
          </div>
          <div className="pref-item">
            <label>Animations</label>
            <label className="toggle-row">
              <input type="checkbox" defaultChecked={!document.documentElement.classList.contains('no-animations')} onChange={e => { document.documentElement.classList.toggle('no-animations', !e.target.checked); localStorage.setItem('animations', e.target.checked ? 'on' : 'off') }} />
              <span className="toggle-label">{document.documentElement.classList.contains('no-animations') ? 'Disabled' : 'Enabled'}</span>
            </label>
          </div>
        </div>
      </section>
    </div>
  )
}
