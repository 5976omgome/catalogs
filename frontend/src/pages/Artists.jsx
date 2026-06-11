import { useState, useEffect, useCallback } from 'react'
import { Upload, Download, Search, Filter, X, ChevronUp, ChevronDown, FileText, Calendar, Mail } from 'lucide-react'
import './Artists.css'

const STATUSES = ['Not Sent', 'Email Sent', 'Follow Up Sent', 'Moving Forward', 'Wrong Email', 'Incorrect Email', 'No Email']
const STATUS_COLORS = { 'Not Sent': 'neutral', 'Email Sent': 'blue', 'Follow Up Sent': 'peach', 'Moving Forward': 'green', 'Wrong Email': 'red', 'Incorrect Email': 'red', 'No Email': 'grey' }
const MOMENTUM_COLORS = { 'Explosive Growth': 'bright-green', 'Growth': 'green', 'Steady': 'grey', 'Slowing': 'blue', 'Cooling': 'red' }

// Gmail-style label colors — cycles through for each week
const WEEK_COLORS = ['#d50000','#f4511e','#e67c73','#f6bf26','#33b679','#039be5','#7986cb','#8e24aa','#616161','#a79b8e']

const DEFAULT_COLS = ['artist_name', 'solo_group', 'emails', 'instagram', 'monthly_listeners', 'momentum', 'status', 'associated_labels', 'region', 'genres']
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

function getWeekColor(weekLabel, allWeeks) {
  const idx = allWeeks.indexOf(weekLabel)
  return WEEK_COLORS[idx % WEEK_COLORS.length]
}

export default function Artists() {
  const [artists, setArtists] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('all')
  const [filters, setFilters] = useState({ momentum: '', status: '', search: '', min_listeners: '', max_listeners: '', region: '' })
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
  const [selected, setSelected] = useState(new Set())

  function toggleSelect(id) {
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  function selectAll() {
    setSelected(prev => prev.size === artists.length ? new Set() : new Set(artists.map(a => a.id)))
  }
  async function batchSetStatus(status) {
    const ids = [...selected]
    if (!ids.length) return
    await fetch('/api/artists/batch-update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, status }) })
    setArtists(prev => prev.map(a => selected.has(a.id) ? { ...a, status } : a))
    setSelected(new Set())
  }

  const fetchArtists = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ page, per_page: 100, sort: sort.col, dir: sort.dir })
    if (activeTab !== 'all') params.set('batch_label', activeTab)
    Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v) })
    try {
      const r = await fetch(`/api/artists/list?${params}`)
      const d = await r.json()
      setArtists(d.artists || [])
      setTotal(d.total || 0)
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [page, sort, filters, activeTab])

  useEffect(() => { fetchArtists() }, [fetchArtists])
  useEffect(() => {
    fetch('/api/artists/stats').then(r => r.json()).then(d => setStats(d)).catch(() => {})
  }, [total, activeTab])

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
      else alert(d.error || 'Import failed')
    } catch (e) { console.error(e) }
    setImporting(false)
    e.target.value = ''
  }

  function handleExport() {
    const params = new URLSearchParams()
    if (activeTab !== 'all') params.set('batch_label', activeTab)
    Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v) })
    window.open(`/api/artists/export?${params}`, '_blank')
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
                {STATUSES.map(s => <option key={s} className={`pill-opt pill-${STATUS_COLORS[s]}`} onClick={() => updateStatus(a.id, s)}>{s}</option>)}
              </div>
            )}
          </div>
        )
      case 'momentum':
        return val ? <span className={`pill-tag pill-${MOMENTUM_COLORS[val] || 'grey'}`}>{val}</span> : ''
      case 'batch_label':
        if (!val) return ''
        const wColor = getWeekColor(val, stats.batches)
        return <span className="pill-tag pill-week" style={{'--week-color': wColor}}><Calendar size={9} />{val.replace('Week Of ', '')}</span>
      case 'solo_group':
        if (!val) return ''
        const tc = val === 'License' ? 'green' : val === 'Buyout' ? 'peach' : val === 'A&R' ? 'blue' : 'neutral'
        return <span className={`pill-tag pill-${tc}`}>{val}</span>
      case 'monthly_listeners':
        return <span className="mono">{(val || 0).toLocaleString()}</span>
      case 'spotify_link':
        return val ? <a href={val} target="_blank" rel="noopener" className="at-link">Open</a> : ''
      case 'instagram':
        return val ? <a href={val} target="_blank" rel="noopener" className="at-link">{val.replace(/https?:\/\/(www\.)?instagram\.com\//,'').replace('/','')}</a> : ''
      case 'emails':
        return val ? <span className="email-cell" title={val}><Mail size={10} />{val.split(',')[0].trim()}</span> : ''
      case 'notes':
        return val ? <span className="notes-cell" title={val}>{val.split('\n')[0].substring(0, 40)}</span> : ''
      case 'career_stage':
        return val ? <span className="pill-tag pill-neutral">{val}</span> : ''
      default:
        return val || ''
    }
  }

  return (
    <div className="artists-page" onClick={() => { setEditingStatus(null); setShowColExport(false) }}>
      {/* Toolbar */}
      <div className="at-toolbar">
        <div className="at-toolbar-left">
          <span className="at-count">{total.toLocaleString()} ARTISTS</span>
          <div className="at-search">
            <Search size={12} />
            <input placeholder="Search artists..." value={filters.search} onChange={e => { setFilters(f => ({ ...f, search: e.target.value })); setPage(1) }} />
          </div>
        </div>
        <div className="at-toolbar-right">
          <button className="at-btn" onClick={e => { e.stopPropagation(); setShowFilters(!showFilters) }}><Filter size={11} /> Filters</button>
          <button className="at-btn" onClick={e => { e.stopPropagation(); setShowColPicker(!showColPicker) }}>Columns</button>
          <button className="at-btn" onClick={e => { e.stopPropagation(); setShowImport(true) }}><Upload size={11} /> Import</button>
          <div className="at-export-wrap">
            <button className="at-btn" onClick={e => { e.stopPropagation(); setShowColExport(!showColExport) }}><Download size={11} /> Export</button>
            {showColExport && (
              <div className="at-export-dropdown" onClick={e => e.stopPropagation()}>
                <button className="pill-opt" onClick={() => { handleExport(); setShowColExport(false) }}>Export Current View</button>
                <div className="at-export-divider" />
                <span className="at-export-label">SINGLE COLUMN</span>
                {ALL_COLS.filter(c => c.key !== 'chartmetric_id').map(c => (
                  <button key={c.key} className="pill-opt" onClick={() => { window.open(`/api/artists/export-column/${c.key}`,'_blank'); setShowColExport(false) }}>{c.label}</button>
                ))}
              </div>
            )}
          </div>
          <button className="at-btn at-btn-report" onClick={() => window.open('/api/reports/summary','_blank')}><FileText size={11} /> Report</button>
        </div>
      </div>

      {/* Week Tabs */}
      <div className="at-tabs">
        <button className={`at-tab ${activeTab === 'all' ? 'active' : ''}`} onClick={() => { setActiveTab('all'); setPage(1) }}>
          All
        </button>
        {stats.batches.map((b, i) => (
          <button key={b} className={`at-tab ${activeTab === b ? 'active' : ''}`} onClick={() => { setActiveTab(b); setPage(1) }}
            style={{'--tab-color': WEEK_COLORS[i % WEEK_COLORS.length]}}>
            <span className="at-tab-dot" />
            {b.replace('Week Of ', '')}
          </button>
        ))}
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="at-filters">
          <select value={filters.momentum} onChange={e => { setFilters(f => ({ ...f, momentum: e.target.value })); setPage(1) }}>
            <option value="">All Momentum</option>
            {stats.momentums.map(m => <option key={m}>{m}</option>)}
          </select>
          <select value={filters.status} onChange={e => { setFilters(f => ({ ...f, status: e.target.value })); setPage(1) }}>
            <option value="">All Status</option>
            {STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
          <select value={filters.region} onChange={e => { setFilters(f => ({ ...f, region: e.target.value })); setPage(1) }}>
            <option value="">All Regions</option>
            {stats.regions.map(r => <option key={r}>{r}</option>)}
          </select>
          <input type="number" placeholder="Min listeners" style={{width:100}} value={filters.min_listeners} onChange={e => { setFilters(f => ({ ...f, min_listeners: e.target.value })); setPage(1) }} />
          <input type="number" placeholder="Max listeners" style={{width:100}} value={filters.max_listeners} onChange={e => { setFilters(f => ({ ...f, max_listeners: e.target.value })); setPage(1) }} />
          <button className="at-btn-clear" onClick={() => { setFilters({ momentum:'',status:'',search:'',min_listeners:'',max_listeners:'',region:'' }); setPage(1) }}><X size={9} /> Clear</button>
        </div>
      )}

      {/* Column picker */}
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

      {/* Batch action bar */}
      {selected.size > 0 && (
        <div className="at-batch-bar">
          <span className="at-batch-count">{selected.size} selected</span>
          {STATUSES.map(s => (
            <button key={s} className={`pill-tag pill-${STATUS_COLORS[s] || 'neutral'} at-batch-btn`} onClick={() => batchSetStatus(s)}>{s}</button>
          ))}
          <button className="at-btn-clear" onClick={() => setSelected(new Set())}><X size={9} /> Deselect</button>
        </div>
      )}

      {/* Table */}
      <div className="at-table-wrap">
        <table className="at-table">
          <thead><tr>
            <th className="at-th-check"><input type="checkbox" checked={selected.size === artists.length && artists.length > 0} onChange={selectAll} /></th>
            {ALL_COLS.filter(c => visibleCols.includes(c.key)).map(c => (
              <th key={c.key} onClick={() => handleSort(c.key)} className={sort.col === c.key ? 'sorted' : ''}>
                {c.label}{sort.col === c.key && (sort.dir === 'asc' ? <ChevronUp size={9} /> : <ChevronDown size={9} />)}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {loading && <tr><td colSpan={visibleCols.length + 1} className="at-loading">Loading...</td></tr>}
            {!loading && !artists.length && <tr><td colSpan={visibleCols.length + 1} className="at-empty">No artists in this view.</td></tr>}
            {!loading && artists.map(a => (
              <tr key={a.id} className={selected.has(a.id) ? 'at-selected' : ''}>
                <td className="at-td-check"><input type="checkbox" checked={selected.has(a.id)} onChange={() => toggleSelect(a.id)} /></td>
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

      {/* Import Modal */}
      {showImport && (
        <div className="at-modal-overlay" onClick={() => setShowImport(false)}>
          <div className="at-modal" onClick={e => e.stopPropagation()}>
            <h3>IMPORT ARTISTS</h3>
            <p>Upload your scout sheet. The "Search" column date is auto-extracted as the Week tag.</p>
            <div className="at-import-field">
              <label>Week Tag (auto-detected from Search column if present)</label>
              <input placeholder="Week Of 06/07" value={importBatch} onChange={e => setImportBatch(e.target.value)} />
            </div>
            <label className="at-import-btn">
              <input type="file" accept=".csv,.tsv" onChange={handleImport} style={{ display: 'none' }} />
              <span>{importing ? 'IMPORTING...' : 'SELECT FILE'}</span>
            </label>
            <button className="at-modal-close" onClick={() => setShowImport(false)}><X size={14} /></button>
          </div>
        </div>
      )}
    </div>
  )
}
