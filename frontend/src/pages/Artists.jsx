import { useState, useEffect, useCallback } from 'react'
import { Upload, Download, Search, Filter, X, ChevronUp, ChevronDown, FileText, Calendar, Mail } from 'lucide-react'
import './Artists.css'

const STATUSES = ['Not Sent', 'Email Sent', 'Follow Up Sent', 'Moving Forward', 'Wrong Email']
const STATUS_COLORS = { 'Not Sent': 'neutral', 'Email Sent': 'blue', 'Follow Up Sent': 'peach', 'Moving Forward': 'green', 'Wrong Email': 'red' }
const MOMENTUM_COLORS = { 'Explosive Growth': 'bright-green', 'Growth': 'green', 'Steady': 'grey', 'Slowing': 'blue', 'Cooling': 'red' }

const DEFAULT_COLS = ['artist_name', 'solo_group', 'emails', 'instagram', 'monthly_listeners', 'momentum', 'status', 'associated_labels', 'region', 'genres', 'batch_label']
const ALL_COLS = [
  { key: 'artist_name', label: 'Artist' },
  { key: 'solo_group', label: 'Type' },
  { key: 'emails', label: 'Emails' },
  { key: 'instagram', label: 'Instagram' },
  { key: 'spotify_link', label: 'Spotify' },
  { key: 'monthly_listeners', label: 'Monthly' },
  { key: 'momentum', label: 'Growth' },
  { key: 'status', label: 'Status' },
  { key: 'associated_labels', label: 'Labels' },
  { key: 'region', label: 'Region' },
  { key: 'genres', label: 'Genre/Scene' },
  { key: 'batch_label', label: 'Week' },
  { key: 'notes', label: 'Notes' },
  { key: 'career_stage', label: 'Career' },
  { key: 'country', label: 'Country' },
  { key: 'facebook', label: 'Facebook' },
  { key: 'first_release', label: '1st Release' },
  { key: 'latest_release', label: 'Latest' },
  { key: 'chartmetric_id', label: 'CM ID' },
]

export default function Artists() {
  const [artists, setArtists] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ momentum: '', status: '', batch_label: '', search: '', min_listeners: '', max_listeners: '', region: '' })
  const [sort, setSort] = useState({ col: 'imported_at', dir: 'desc' })
  const [visibleCols, setVisibleCols] = useState(DEFAULT_COLS)
  const [showColPicker, setShowColPicker] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [stats, setStats] = useState({ total: 0, momentums: [], regions: [], batches: [], statuses: [] })
  const [showImport, setShowImport] = useState(false)
  const [importBatch, setImportBatch] = useState('')
  const [importing, setImporting] = useState(false)
  const [editingStatus, setEditingStatus] = useState(null)
  const [showColExport, setShowColExport] = useState(false)

  const fetchArtists = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ page, per_page: 100, sort: sort.col, dir: sort.dir })
    Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v) })
    try {
      const r = await fetch(`/api/artists/list?${params}`)
      const d = await r.json()
      setArtists(d.artists || [])
      setTotal(d.total || 0)
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [page, sort, filters])

  useEffect(() => { fetchArtists() }, [fetchArtists])
  useEffect(() => {
    fetch('/api/artists/stats').then(r => r.json()).then(d => setStats(d)).catch(() => {})
  }, [total])

  function handleSort(col) {
    setSort(s => s.col === col ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' })
    setPage(1)
  }

  async function updateStatus(id, status) {
    await fetch(`/api/artists/update/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
    setArtists(prev => prev.map(a => a.id === id ? { ...a, status } : a))
    setEditingStatus(null)
  }

  async function handleImport(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('batch_label', importBatch)
    try {
      const r = await fetch('/api/artists/import', { method: 'POST', body: fd })
      const d = await r.json()
      if (d.ok) { fetchArtists(); setShowImport(false); setImportBatch('') }
      else { alert(d.error || 'Import failed') }
    } catch (e) { console.error(e) }
    setImporting(false)
    e.target.value = ''
  }

  function renderCell(a, col) {
    const val = a[col.key]
    switch (col.key) {
      case 'status':
        return (
          <div className="pill-cell">
            <span className={`pill-tag pill-${STATUS_COLORS[val] || 'neutral'}`} onClick={e => { e.stopPropagation(); setEditingStatus(editingStatus === a.id ? null : a.id) }}>
              {val || 'Not Sent'}
            </span>
            {editingStatus === a.id && (
              <div className="pill-dropdown" onClick={e => e.stopPropagation()}>
                {STATUSES.map(s => (
                  <button key={s} className={`pill-opt pill-${STATUS_COLORS[s]}`} onClick={() => updateStatus(a.id, s)}>{s}</button>
                ))}
              </div>
            )}
          </div>
        )
      case 'momentum':
        return val ? <span className={`pill-tag pill-${MOMENTUM_COLORS[val] || 'neutral'}`}>{val}</span> : ''
      case 'batch_label':
        return val ? <span className="pill-tag pill-date"><Calendar size={8} />{val}</span> : ''
      case 'solo_group':
        if (!val) return ''
        const typeColor = val === 'License' ? 'green' : val === 'Buyout' ? 'peach' : val === 'A&R' ? 'blue' : 'neutral'
        return <span className={`pill-tag pill-${typeColor}`}>{val}</span>
      case 'monthly_listeners':
        return <span className="mono">{(val || 0).toLocaleString()}</span>
      case 'spotify_link':
        return val ? <a href={val} target="_blank" rel="noopener" className="at-link">Open</a> : ''
      case 'instagram':
        return val ? <a href={val} target="_blank" rel="noopener" className="at-link">{val.replace('https://www.instagram.com/','').replace('https://instagram.com/','').replace('/','')}</a> : ''
      case 'emails':
        return val ? <span className="email-cell" title={val}><Mail size={9} />{val.split(',')[0].trim()}</span> : ''
      case 'notes':
        return val ? <span className="notes-cell" title={val}>{val.split('\n')[0].substring(0, 30)}</span> : ''
      case 'career_stage':
        return val ? <span className="pill-tag pill-neutral">{val}</span> : ''
      default:
        return val || ''
    }
  }

  return (
    <div className="artists-page" onClick={() => { setEditingStatus(null); setShowColExport(false) }}>
      <div className="at-toolbar">
        <div className="at-toolbar-left">
          <span className="at-count">{total.toLocaleString()} ARTISTS</span>
          <div className="at-search">
            <Search size={10} />
            <input placeholder="Search..." value={filters.search} onChange={e => { setFilters(f => ({ ...f, search: e.target.value })); setPage(1) }} />
          </div>
        </div>
        <div className="at-toolbar-right">
          <button className="at-btn" onClick={e => { e.stopPropagation(); setShowFilters(!showFilters) }}><Filter size={10} /> Filters</button>
          <button className="at-btn" onClick={e => { e.stopPropagation(); setShowColPicker(!showColPicker) }}>Columns</button>
          <button className="at-btn" onClick={e => { e.stopPropagation(); setShowImport(true) }}><Upload size={10} /> Import</button>
          <div className="at-export-wrap">
            <button className="at-btn" onClick={e => { e.stopPropagation(); setShowColExport(!showColExport) }}><Download size={10} /> Export</button>
            {showColExport && (
              <div className="at-export-dropdown" onClick={e => e.stopPropagation()}>
                <button className="pill-opt" onClick={() => { window.open('/api/artists/export','_blank'); setShowColExport(false) }}>Export All (CSV)</button>
                <div className="at-export-divider" />
                <span className="at-export-label">SINGLE COLUMN</span>
                {ALL_COLS.filter(c => c.key !== 'chartmetric_id').map(c => (
                  <button key={c.key} className="pill-opt" onClick={() => { window.open(`/api/artists/export-column/${c.key}`,'_blank'); setShowColExport(false) }}>{c.label}</button>
                ))}
              </div>
            )}
          </div>
          <button className="at-btn at-btn-report" onClick={() => window.open('/api/reports/summary','_blank')}><FileText size={10} /> Report</button>
        </div>
      </div>

      {showFilters && (
        <div className="at-filters">
          <select value={filters.momentum} onChange={e => { setFilters(f => ({ ...f, momentum: e.target.value })); setPage(1) }}>
            <option value="">Momentum</option>
            {stats.momentums.map(m => <option key={m}>{m}</option>)}
          </select>
          <select value={filters.status} onChange={e => { setFilters(f => ({ ...f, status: e.target.value })); setPage(1) }}>
            <option value="">Status</option>
            {STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
          <select value={filters.region} onChange={e => { setFilters(f => ({ ...f, region: e.target.value })); setPage(1) }}>
            <option value="">Region</option>
            {stats.regions.map(r => <option key={r}>{r}</option>)}
          </select>
          <select value={filters.batch_label} onChange={e => { setFilters(f => ({ ...f, batch_label: e.target.value })); setPage(1) }}>
            <option value="">Week</option>
            {stats.batches.map(b => <option key={b}>{b}</option>)}
          </select>
          <input type="number" placeholder="Min" style={{width:55}} value={filters.min_listeners} onChange={e => { setFilters(f => ({ ...f, min_listeners: e.target.value })); setPage(1) }} />
          <input type="number" placeholder="Max" style={{width:55}} value={filters.max_listeners} onChange={e => { setFilters(f => ({ ...f, max_listeners: e.target.value })); setPage(1) }} />
          <button className="at-btn-clear" onClick={() => { setFilters({ momentum:'',status:'',batch_label:'',search:'',min_listeners:'',max_listeners:'',region:'' }); setPage(1) }}><X size={8} /> Clear</button>
        </div>
      )}

      {showColPicker && (
        <div className="at-col-picker">
          {ALL_COLS.map(c => (
            <label key={c.key} className="at-col-check">
              <input type="checkbox" checked={visibleCols.includes(c.key)} onChange={e => setVisibleCols(e.target.checked ? [...visibleCols, c.key] : visibleCols.filter(x => x !== c.key))} />
              <span>{c.label}</span>
            </label>
          ))}
        </div>
      )}

      <div className="at-table-wrap">
        <table className="at-table">
          <thead><tr>
            {ALL_COLS.filter(c => visibleCols.includes(c.key)).map(c => (
              <th key={c.key} onClick={() => handleSort(c.key)} className={sort.col === c.key ? 'sorted' : ''}>
                {c.label}{sort.col === c.key && (sort.dir === 'asc' ? <ChevronUp size={8} /> : <ChevronDown size={8} />)}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {loading && <tr><td colSpan={visibleCols.length} className="at-loading">Loading...</td></tr>}
            {!loading && !artists.length && <tr><td colSpan={visibleCols.length} className="at-empty">No artists. Click Import to upload a CSV.</td></tr>}
            {!loading && artists.map(a => (
              <tr key={a.id}>
                {ALL_COLS.filter(c => visibleCols.includes(c.key)).map(c => (
                  <td key={c.key}>{renderCell(a, c)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {total > 100 && (
        <div className="at-pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
          <span>{page} / {Math.ceil(total / 100)}</span>
          <button disabled={page >= Math.ceil(total / 100)} onClick={() => setPage(p => p + 1)}>Next →</button>
        </div>
      )}

      {showImport && (
        <div className="at-modal-overlay" onClick={() => setShowImport(false)}>
          <div className="at-modal" onClick={e => e.stopPropagation()}>
            <h3>IMPORT ARTISTS</h3>
            <p>Upload your scout sheet (.csv or .tsv). Auto-maps: Artist Name, Type, Emails, Instagram, Spotify, Monthly, Growth, Status, Label Info, Region, Genre/Scene. The "Search" column date is auto-extracted as the Week tag.</p>
            <div className="at-import-field">
              <label>Week Tag (optional — auto-detected from Search column)</label>
              <input placeholder="Week Of 06/07" value={importBatch} onChange={e => setImportBatch(e.target.value)} />
            </div>
            <label className="at-import-btn">
              <input type="file" accept=".csv,.tsv" onChange={handleImport} style={{ display: 'none' }} />
              <span>{importing ? 'IMPORTING...' : 'SELECT FILE'}</span>
            </label>
            <button className="at-modal-close" onClick={() => setShowImport(false)}><X size={12} /></button>
          </div>
        </div>
      )}
    </div>
  )
}
