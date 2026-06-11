import { useState, useEffect } from 'react'
import { Key, Check, X, Clock, Download } from 'lucide-react'
import './Settings.css'

const KEY_SLOTS = [
  { id: 'genius_1', label: 'Genius Token 1', service: 'genius', slot: 1 },
  { id: 'genius_2', label: 'Genius Token 2', service: 'genius', slot: 2 },
  { id: 'genius_3', label: 'Genius Token 3', service: 'genius', slot: 3 },
  { id: 'genius_4', label: 'Genius Token 4', service: 'genius', slot: 4 },
  { id: 'groq', label: 'Groq API Key', service: 'groq', slot: 1 },
  { id: 'gemini', label: 'Gemini API Key', service: 'gemini', slot: 1 },
]

const STATUS_ONLY = [
  { id: 'itunes', label: 'iTunes', status: true },
  { id: 'deezer', label: 'Deezer', status: true },
]

export default function Settings() {
  const [keys, setKeys] = useState({})
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState({})
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone)
  const [emails, setEmails] = useState(['gavin@ignitethelabel.com', 'gavin.roy07@ignitethelabel.com'])

  useEffect(() => {
    fetch('/api/settings/keys')
      .then(r => r.ok ? r.json() : { keys: {} })
      .then(d => setKeys(d.keys || {}))
      .catch(() => {})
  }, [])

  async function saveKey(slotId, service, slot) {
    const val = values[slotId]
    if (!val || !val.trim()) return
    setSaving(s => ({ ...s, [slotId]: 'saving' }))
    try {
      const r = await fetch('/api/settings/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, slot, key: val.trim() }),
      })
      const d = await r.json()
      if (r.ok) {
        setSaving(s => ({ ...s, [slotId]: d.valid ? 'valid' : 'invalid' }))
        setKeys(k => ({ ...k, [slotId]: { set: true, valid: d.valid, masked: d.masked } }))
        setValues(v => ({ ...v, [slotId]: '' }))
      } else {
        setSaving(s => ({ ...s, [slotId]: 'error' }))
      }
    } catch {
      setSaving(s => ({ ...s, [slotId]: 'error' }))
    }
    setTimeout(() => setSaving(s => ({ ...s, [slotId]: null })), 2500)
  }

  return (
    <div className="settings">
      <div className="settings-header">
        <h1>Settings</h1>
        <p>API keys, preferences, and platform configuration</p>
      </div>

      {/* API Keys */}
      <section className="settings-section">
        <h2><Key size={14} /> API Keys</h2>
        <p className="settings-hint">Genius keys auto-rotate when one hits a rate limit. Keys are validated on save.</p>
        <div className="key-grid">
          {KEY_SLOTS.map(slot => (
            <div className="key-slot" key={slot.id}>
              <label>{slot.label}</label>
              <div className="key-input-row">
                <input
                  type="password"
                  placeholder={keys[slot.id]?.masked || 'Paste key...'}
                  value={values[slot.id] || ''}
                  onChange={e => setValues(v => ({ ...v, [slot.id]: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && saveKey(slot.id, slot.service, slot.slot)}
                />
                <button className="key-save" onClick={() => saveKey(slot.id, slot.service, slot.slot)}>
                  {saving[slot.id] === 'saving' ? '...' : 'SAVE'}
                </button>
                <span className={`key-status ${saving[slot.id] || (keys[slot.id]?.set ? (keys[slot.id]?.valid ? 'valid' : 'invalid') : '')}`}>
                  {saving[slot.id] === 'valid' || keys[slot.id]?.valid ? <Check size={14} /> : null}
                  {saving[slot.id] === 'invalid' || (keys[slot.id]?.set && !keys[slot.id]?.valid) ? <X size={14} /> : null}
                </span>
              </div>
            </div>
          ))}
          {STATUS_ONLY.map(s => (
            <div className="key-slot status-slot" key={s.id}>
              <label>{s.label}</label>
              <div className="key-input-row">
                <span className="status-indicator ok"><Check size={14} /> Available (no key required)</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Preferences */}
      <section className="settings-section">
        <h2><Clock size={14} /> Preferences</h2>
        <div className="pref-grid">
          <div className="pref-item">
            <label>Timezone (auto-detected)</label>
            <input type="text" value={timezone} readOnly style={{opacity:.7,cursor:'default'}} />
          </div>
          <div className="pref-item">
            <label>Scouting Email 1</label>
            <input type="email" value={emails[0]} onChange={e => setEmails([e.target.value, emails[1]])} />
          </div>
          <div className="pref-item">
            <label>Scouting Email 2</label>
            <input type="email" value={emails[1]} onChange={e => setEmails([emails[0], e.target.value])} />
          </div>
        </div>
      </section>

      {/* Export */}
      <section className="settings-section">
        <h2><Download size={14} /> Export Format</h2>
        <p className="settings-hint">Configure which columns appear in CSV exports. (Coming in Phase 2)</p>
      </section>
    </div>
  )
}
