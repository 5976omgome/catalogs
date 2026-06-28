import { useState, useRef, useCallback } from 'react'
import { UploadCloud, FileSpreadsheet, Download, RotateCcw, ShieldCheck, Copy, Layers, X } from 'lucide-react'
import './CrossCheck.css'

// Build an RFC-4180-ish CSV string from headers + rows (handles quoting).
function buildCSV(headers, rows) {
  const esc = v => {
    const s = v == null ? '' : String(v)
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [headers.map(esc).join(',')]
  for (const r of rows) lines.push(r.map(esc).join(','))
  return lines.join('\r\n')
}

function Stat({ icon, label, value, tone }) {
  return (
    <div className={`cc-stat ${tone ? 'cc-stat-' + tone : ''}`}>
      <span className="cc-stat-ic">{icon}</span>
      <span className="cc-stat-val">{Number(value).toLocaleString()}</span>
      <span className="cc-stat-lbl">{label}</span>
    </div>
  )
}

export default function CrossCheck() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState('')
  const inputRef = useRef(null)

  const scan = useCallback(async file => {
    if (!file) return
    setLoading(true); setError(''); setResult(null); setFileName(file.name)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch('/api/artists/crosscheck', { method: 'POST', body: fd })
      const d = await r.json()
      if (d.ok) setResult(d)
      else setError((d.error || 'Scan failed') + (d.headers_seen ? ` — columns found: ${d.headers_seen.join(', ')}` : ''))
    } catch (e) { setError('Scan failed: ' + e.message) }
    setLoading(false)
  }, [])

  function onDrop(e) {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) scan(f)
  }

  function download() {
    if (!result) return
    const csv = buildCSV(result.headers, result.rows)
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = result.filename; a.click()
    URL.revokeObjectURL(url)
  }

  function reset() {
    setResult(null); setError(''); setFileName('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const flagIdx = result ? result.headers.length - 1 : -1
  const artistIdx = result ? result.headers.findIndex(h => h === result.artist_column) : -1

  return (
    <div className="cc-page">
      <header className="cc-header">
        <div className="cc-header-icon"><Copy size={18} /></div>
        <div className="cc-header-text">
          <h1 className="cc-title">CROSS CHECK</h1>
          <p className="cc-sub">Scan a table against your library for duplicate artists — nothing is saved.</p>
        </div>
      </header>

      {!result && (
        <div
          className={`cc-drop ${dragging ? 'dragging' : ''} ${loading ? 'loading' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !loading && inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".csv,.tsv" hidden
            onChange={e => { const f = e.target.files?.[0]; if (f) scan(f) }} />
          <div className="cc-drop-inner">
            {loading ? (
              <>
                <div className="cc-spinner" />
                <span className="cc-drop-title">SCANNING {fileName}…</span>
              </>
            ) : (
              <>
                <UploadCloud size={36} className="cc-drop-ic" />
                <span className="cc-drop-title">DROP A TABLE OR CLICK TO UPLOAD</span>
                <span className="cc-drop-hint">.csv or .tsv · must include an Artist column</span>
              </>
            )}
          </div>
        </div>
      )}

      {error && <div className="cc-error"><X size={13} /> {error}</div>}

      {result && (
        <div className="cc-results">
          <div className="cc-summary">
            <Stat icon={<Layers size={14} />} label="Rows" value={result.summary.total} />
            <Stat icon={<Copy size={14} />} label="Flagged" value={result.summary.flagged} tone="accent" />
            <Stat icon={<ShieldCheck size={14} />} label="Library" value={result.summary.library_dupes} tone="warn" />
            <Stat icon={<FileSpreadsheet size={14} />} label="In File" value={result.summary.file_dupes} tone="warn" />
            <Stat icon={<ShieldCheck size={14} />} label="Clean" value={result.summary.clean} tone="ok" />
            <div className="cc-actions">
              <button className="cc-btn primary" onClick={download}><Download size={13} /> Download CSV</button>
              <button className="cc-btn" onClick={reset}><RotateCcw size={12} /> New Scan</button>
            </div>
          </div>

          <div className="cc-meta">
            Checked <b>{fileName}</b> against <b>{result.summary.library_size.toLocaleString()}</b> library artists · matched on the <b>{result.artist_column}</b> column
          </div>

          <div className="cc-table-wrap">
            <table className="cc-table">
              <thead>
                <tr>
                  {result.headers.map((h, i) => (
                    <th key={i} className={i === flagIdx ? 'cc-flag-col' : ''}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, ri) => (
                  <tr key={ri} className={row[flagIdx] ? 'cc-row-flagged' : ''}>
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className={`${ci === flagIdx ? 'cc-flag-cell' : ''} ${ci === artistIdx ? 'cc-artist-cell' : ''}`}
                      >
                        {ci === flagIdx && cell
                          ? <span className="cc-flag-pill">{cell}</span>
                          : <span className="cc-cell-text" title={cell}>{cell}</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
