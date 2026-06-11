import { useState, useEffect, useCallback } from 'react'
import { Upload, Download, Search, Filter, X, ChevronUp, ChevronDown, FileText } from 'lucide-react'
import './Artists.css'

const STATUSES = ['Not Sent', 'Email Sent', 'Follow Up Sent', 'Moving Forward', 'Wrong Email']
const DEFAULT_COLS = ['artist_name', 'status', 'monthly_listeners', 'momentum', 'region', 'genres', 'associated_labels', 'batch_label']
const ALL_COLS = [
  { key: 'artist_name', label: 'Artist' },
  { key: 'status', label: 'Status' },
  { key: 'batch_label', label: 'Batch' },
  { key: 'monthly_listeners', label: 'Monthly' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'region', label: 'Region' },
  { key: 'genres', label: 'Genres' },
  { key: 'associated_labels', label: 'Labels' },
  { key: 'career_stage', label: 'Career' },
  { key: 'country', label: 'Country' },
  { key: 'emails', label: 'Emails' },
  { key: 'instagram', label: 'Instagram' },
  { key: 'spotify_link', label: 'Spotify' },
  { key: 'pronouns', label: 'Pronouns' },
  { key: 'solo_group', label: 'Type' },
  { key: 'first_release', label: 'First Release' },
  { key: 'latest_release', label: 'Latest Release' },
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
      if (d.ok) { fetchArtists(); setShowImport(false) }
    } catch (e) { console.error(e) }
    setImporting(false)
    e.target.value = ''
  }

  async function exportCSV() {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v) })
    window.open(`/api/artists/export?${params}`, '_blank')
  }

  async function generateReport() {
    window.open('/api/reports/summary', '_blank')
  }

  return (
    <div className="artists-page">
      {/* Toolbar */}
      <div className="at-toolbar">
        <div className="at-toolbar-left">
          <span className="at-count">{total.toLocaleString()} artists</span>
          <div className="at-search">
            <Search size={12} />
            <input placeholder="Search artists..." value={filters.search} onChange={e => { setFilters(f => ({ ...f, search: e.target.value })); setPage(1) }} />
          </div>
        </div>
        <div className="at-toolbar-right">
          <button className="at-btn" onClick={() => setShowFilters(!showFilters)}><Filter size={12} /> Filters</button>
          <button className="at-btn" onClick={() => setShowColPicker(!showColPicker)}>Columns</button>
          <button className="at-btn" onClick={() => setShowImport(true)}><Upload size={12} /> Import</button>
          <button className="at-btn" onClick={exportCSV}><Download size={12} /> Export</button>
          <button className="at-btn at-btn-report" onClick={generateReport}><FileText size={12} /> Report</button>
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="at-filters">
          <select value={filters.momentum} onChange={e => { setFilters(f => ({ ...f, momentum: e.target.value })); setPage(1) }}>
            <option value="">All Momentum</option>
            {stats.momentums.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={filters.status} onChange={e => { setFilters(f => ({ ...f, status: e.target.value })); setPage(1) }}>
            <option value="">All Status</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filters.region} onChange={e => { setFilters(f => ({ ...f, region: e.target.value })); setPage(1) }}>
            <option value="">All Regions</option>
            {stats.regions.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <select value={filters.batch_label} onChange={e => { setFilters(f => ({ ...f, batch_label: e.target.value })); setPage(1) }}>
            <option value="">All Batches</option>
            {stats.batches.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <input type="number" placeholder="Min listeners" value={filters.min_listeners} onChange={e => { setFilters(f => ({ ...f, min_listeners: e.target.value })); setPage(1) }} />
          <input type="number" placeholder="Max listeners" value={filters.max_listeners} onChange={e => { setFilters(f => ({ ...f, max_listeners: e.target.value })); setPage(1) }} />
          <button className="at-btn-clear" onClick={() => { setFilters({ momentum: '', status: '', batch_label: '', search: '', min_listeners: '', max_listeners: '', region: '' }); setPage(1) }}><X size={10} /> Clear</button>
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

      {/* Table */}
      <div className="at-table-wrap">
        <table className="at-table">
          <thead>
            <tr>
              {ALL_COLS.filter(c => visibleCols.includes(c.key)).map(c => (
                <th key={c.key} onClick={() => handleSort(c.key)} className={sort.col === c.key ? 'sorted' : ''}>
                  {c.label}
                  {sort.col === c.key && (sort.dir === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} />)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={visibleCols.length} className="at-loading">Loading...</td></tr>}
            {!loading && artists.length === 0 && <tr><td colSpan={visibleCols.length} className="at-empty">No artists. Import a CSV to get started.</td></tr>}
            {!loading && artists.map(a => (
              <tr key={a.id}>
                {ALL_COLS.filter(c => visibleCols.includes(c.key)).map(c => (
                  <td key={c.key}>
                    {c.key === 'status' ? (
                      <select className="at-status-select" value={a.status} onChange={e => updateStatus(a.id, e.target.value)}>
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    ) : c.key === 'monthly_listeners' ? (
                      (a[c.key] || 0).toLocaleString()
                    ) : c.key === 'spotify_link' && a[c.key] ? (
                      <a href={a[c.key]} target="_blank" rel="noopener" className="at-link">Open</a>
                    ) : (
                      a[c.key] || ''
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 100 && (
        <div className="at-pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</button>
          <span>Page {page} of {Math.ceil(total / 100)}</span>
          <button disabled={page >= Math.ceil(total / 100)} onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      )}

      {/* Import Modal */}
      {showImport && (
        <div className="at-modal-overlay" onClick={() => setShowImport(false)}>
          <div className="at-modal" onClick={e => e.stopPropagation()}>
            <h3>Import Artists CSV</h3>
            <p>Upload a Chartmetric export (.csv or .tsv). Columns are auto-mapped.</p>
            <div className="at-import-field">
              <label>Batch Label (optional)</label>
              <input placeholder="e.g. Week Of 06/07" value={importBatch} onChange={e => setImportBatch(e.target.value)} />
            </div>
            <label className="at-import-btn">
              <input type="file" accept=".csv,.tsv" onChange={handleImport} style={{ display: 'none' }} />
              <span>{importing ? 'Importing...' : 'SELECT FILE'}</span>
            </label>
            <button className="at-modal-close" onClick={() => setShowImport(false)}><X size={14} /></button>
          </div>
        </div>
      )}
    </div>
  )
}
