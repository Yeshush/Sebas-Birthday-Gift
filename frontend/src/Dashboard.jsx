import { useState, useEffect, useMemo, useRef } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

/* ── Category meta ─────────────────────────────── */
const CATEGORIES = [
  { key: 'all',          label: 'Alle',              icon: null,  color: 'var(--mist)' },
  { key: 'retail',       label: 'Retail',             icon: '🛒',  color: 'var(--rust)' },
  { key: 'lager',        label: 'Lager & Logistik',   icon: '📦',  color: 'var(--gold)' },
  { key: 'verkauf',      label: 'Verkauf & Beratung', icon: '🤝',  color: 'var(--sage)' },
  { key: 'gastro',       label: 'Gastronomie',        icon: '🍽',  color: '#8B6E4E'     },
  { key: 'quereinstieg', label: 'Quereinstieg',       icon: '🔄',  color: '#7B5EA7'     },
  { key: 'easy',         label: 'Easy Apply',         icon: '⚡',  color: '#2E7D32'     },
];

const CAT_MAP = Object.fromEntries(CATEGORIES.map(c => [c.key, c]));

/* ── Tag input component ───────────────────────── */
function TagInput({ tags, onChange }) {
  const [input, setInput] = useState('');
  const inputRef = useRef(null);

  const addTag = (raw) => {
    const val = raw.trim().toLowerCase();
    if (val && !tags.includes(val)) {
      onChange([...tags, val]);
    }
    setInput('');
  };

  const removeTag = (tag) => onChange(tags.filter(t => t !== tag));

  const handleKey = (e) => {
    if ((e.key === 'Enter' || e.key === ',') && input.trim()) {
      e.preventDefault();
      addTag(input);
    } else if (e.key === 'Backspace' && !input && tags.length) {
      removeTag(tags[tags.length - 1]);
    }
  };

  return (
    <div className="tag-editor" onClick={() => inputRef.current?.focus()}>
      {tags.map(tag => (
        <span key={tag} className="tag-chip">
          {tag}
          <button className="tag-remove" onClick={(e) => { e.stopPropagation(); removeTag(tag); }} type="button">
            ×
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        className="tag-input-field"
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => input.trim() && addTag(input)}
        placeholder={tags.length ? '' : 'Stichwort eingeben + Enter'}
      />
    </div>
  );
}

/* ── Profile editor modal ──────────────────────── */
function ProfileEditor({ profile, onSave, onClose }) {
  const [educationLevel, setEducationLevel] = useState(profile.education_level || '');
  const [minWorkload,    setMinWorkload]    = useState(profile.min_workload ?? 80);
  const [interests,      setInterests]      = useState([...(profile.interests || [])]);
  const [allowQuer,      setAllowQuer]      = useState(profile.allow_quereinstieg ?? true);
  const [saving,         setSaving]         = useState(false);
  const [error,          setError]          = useState('');

  // close on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.put('/api/profile', {
        education_level:    educationLevel,
        min_workload:       minWorkload,
        interests,
        allow_quereinstieg: allowQuer,
      }, { headers: { Authorization: `Bearer ${token}` } });
      onSave(res.data);
    } catch {
      setError('Speichern fehlgeschlagen. Bitte erneut versuchen.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card">
        <div className="modal-header">
          <h3 className="modal-title">Profil bearbeiten</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="editor-body">
          {/* EFZ field */}
          <div className="editor-field">
            <label className="editor-label">EFZ Ausbildungsfeld</label>
            <p className="editor-hint">z.B. «Detailhandel», «Koch», «Kaufmann» — wird automatisch als Suchbegriff verwendet</p>
            <input
              className="editor-input"
              type="text"
              value={educationLevel}
              onChange={e => setEducationLevel(e.target.value)}
              placeholder="z.B. Detailhandel EFZ"
            />
          </div>

          {/* Min workload */}
          <div className="editor-field">
            <label className="editor-label">Minimales Pensum</label>
            <div className="workload-row">
              <input
                className="workload-range"
                type="range"
                min={10}
                max={100}
                step={10}
                value={minWorkload}
                onChange={e => setMinWorkload(Number(e.target.value))}
              />
              <span className="workload-value">{minWorkload}%</span>
            </div>
          </div>

          {/* Quereinstieg */}
          <div className="editor-field">
            <label className="editor-label">Quereinstieg</label>
            <div className="toggle-row">
              <span className="toggle-desc">Jobs für Quereinsteiger einschliessen</span>
              <label className="toggle-switch">
                <input type="checkbox" checked={allowQuer} onChange={e => setAllowQuer(e.target.checked)} />
                <span className="toggle-track" />
              </label>
            </div>
          </div>

          {/* Interests */}
          <div className="editor-field">
            <label className="editor-label">Interessen / Stichwörter</label>
            <p className="editor-hint">Enter oder Komma zum Hinzufügen, × zum Entfernen</p>
            <TagInput tags={interests} onChange={setInterests} />
          </div>

          {error && <p className="login-error">{error}</p>}

          <div className="editor-actions">
            <button className="btn-cancel" onClick={onClose}>Abbrechen</button>
            <button className="btn-save" onClick={handleSave} disabled={saving}>
              {saving ? 'Speichern…' : 'Speichern →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Single job card ───────────────────────────── */
function JobCard({ job, idx }) {
  const cat = CAT_MAP[job.category] || { color: 'var(--mist)' };
  return (
    <article
      className={`job-card${job.is_promoted ? ' featured' : ''}`}
      style={{
        '--card-accent': cat.color,
        animationDelay: `${Math.min(idx * 0.04, 0.35)}s`,
      }}
    >
      <div className="card-top">
        <div className="card-badges">
          {job.easy_apply   && <span className="badge badge-easy">⚡ Easy Apply</span>}
          {job.is_promoted  && <span className="badge badge-promoted">★ Empfohlen</span>}
        </div>
        <span className="card-cat-dot" style={{ background: cat.color }} />
      </div>

      <h3 className="card-title">{job.title}</h3>
      <p className="card-company">{job.company_clean || job.company}</p>

      <div className="card-details">
        {job.location && (
          <div className="detail-row"><span className="detail-icon">📍</span>{job.location}</div>
        )}
        {job.workload && (
          <div className="detail-row"><span className="detail-icon">⏱</span>{job.workload}</div>
        )}
        {(job.date || job.published) && (
          <div className="detail-row"><span className="detail-icon">📅</span>{job.date || job.published}</div>
        )}
      </div>

      <div className="card-footer">
        <span className="published-tag">{job.date || job.published || ''}</span>
        <a className="apply-btn" href={job.link || job.url} target="_blank" rel="noreferrer">
          Bewerben <span className="arrow">→</span>
        </a>
      </div>
    </article>
  );
}

/* ── Category section (grouped view) ──────────── */
function CategorySection({ catKey, jobs }) {
  const meta = CAT_MAP[catKey] || { label: catKey, color: 'var(--mist)', icon: null };
  return (
    <section className="cat-section">
      <div className="cat-section-header">
        <span className="cat-section-dot" style={{ background: meta.color }} />
        <h2 className="cat-section-title">
          {meta.icon && <>{meta.icon} </>}{meta.label}
        </h2>
        <span className="cat-section-count">{jobs.length} Stelle{jobs.length !== 1 ? 'n' : ''}</span>
      </div>
      <div className="jobs-grid">
        {jobs.map((job, idx) => <JobCard key={job.uuid || idx} job={job} idx={idx} />)}
      </div>
    </section>
  );
}

/* ── Dashboard ─────────────────────────────────── */
export default function Dashboard() {
  const [user,        setUser]        = useState(null);
  const [location,    setLocation]    = useState('winterthur');
  const [maxPages,    setMaxPages]    = useState('');
  const [scraping,    setScraping]    = useState(false);
  const [progress,    setProgress]    = useState(0);
  const [statusMsg,   setStatusMsg]   = useState('');
  const [results,     setResults]     = useState(null);
  const [activeTab,   setActiveTab]   = useState('scrape');
  const [history,     setHistory]     = useState([]);
  const [jobsList,    setJobsList]    = useState(null);
  const [isDark,      setIsDark]      = useState(false);
  const [catFilter,   setCatFilter]   = useState('all');
  const [jobSearch,   setJobSearch]   = useState('');
  const [editProfile, setEditProfile] = useState(false);
  const navigate = useNavigate();

  /* dark mode from localStorage */
  useEffect(() => {
    const saved = localStorage.getItem('darkMode') === 'true';
    setIsDark(saved);
    document.body.classList.toggle('dark-mode', saved);
  }, []);

  /* load user */
  useEffect(() => {
    (async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) throw new Error();
        const res = await axios.get('/api/me', { headers: { Authorization: `Bearer ${token}` } });
        setUser(res.data);
      } catch {
        navigate('/');
      }
    })();
  }, [navigate]);

  /* load history when tab opens */
  useEffect(() => {
    if (activeTab === 'history') fetchHistory();
  }, [activeTab]);

  const fetchHistory = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/history', { headers: { Authorization: `Bearer ${token}` } });
      setHistory(res.data);
    } catch (err) { console.error(err); }
  };

  const fetchJobs = async (searchId) => {
    try {
      setJobsList([]);
      setStatusMsg('Lade Jobs…');
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/history/${searchId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setJobsList(res.data.results);
      setCatFilter('all');
      setJobSearch('');
      setStatusMsg('');
    } catch (err) {
      console.error(err);
      setStatusMsg('Fehler beim Laden der Jobs.');
    }
  };

  const handleScrape = () => {
    setScraping(true);
    setProgress(2);
    setStatusMsg('Scraper wird gestartet…');
    setResults(null);
    setJobsList(null);

    const token = localStorage.getItem('token');
    const url = `/scrape?location=${encodeURIComponent(location)}${maxPages ? `&max_pages=${maxPages}` : ''}&token=${token}`;
    const sse = new EventSource(url);

    sse.addEventListener('found', e => {
      const d = JSON.parse(e.data);
      setProgress(10);
      setStatusMsg(`${d.total} Jobs auf ${d.total_pages} Seiten gefunden.`);
    });
    sse.addEventListener('page', e => {
      const d = JSON.parse(e.data);
      setProgress(d.progress);
      setStatusMsg(`Seite ${d.page} von ${d.total_pages} wird gescrapt…`);
    });
    sse.addEventListener('stage', e => {
      const d = JSON.parse(e.data);
      setProgress(d.progress);
      const rem = d.remaining ?? d.kept ?? '';
      setStatusMsg(`Filtern: ${d.stage}${rem !== '' ? ` (${rem} verbleibend)` : ''}`);
    });
    sse.addEventListener('done', e => {
      const d = JSON.parse(e.data);
      setProgress(100);
      setStatusMsg('Fertig!');
      setResults({ ...d.stats, search_id: d.search_id, easy_count: d.easy_count });
      setScraping(false);
      sse.close();
    });
    sse.addEventListener('error_msg', e => {
      const d = JSON.parse(e.data);
      setStatusMsg(`Fehler: ${d.msg}`);
      setScraping(false);
      sse.close();
    });
    sse.onerror = () => { sse.close(); setScraping(false); };
  };

  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    localStorage.setItem('darkMode', String(next));
    document.body.classList.toggle('dark-mode', next);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/');
  };

  const handleProfileSaved = (updatedProfile) => {
    setUser(prev => ({ ...prev, profile: updatedProfile }));
    setEditProfile(false);
  };

  /* filter + group jobs */
  const filteredJobs = useMemo(() => {
    if (!jobsList) return [];
    return jobsList.filter(job => {
      const q = jobSearch.toLowerCase();
      const matchSearch = !q ||
        (job.title   || '').toLowerCase().includes(q) ||
        (job.company || '').toLowerCase().includes(q);
      const matchCat = catFilter === 'all' ||
        (catFilter === 'easy' ? job.easy_apply : job.category === catFilter);
      return matchSearch && matchCat;
    });
  }, [jobsList, jobSearch, catFilter]);

  /* group by category for the "Alle" view */
  const groupedJobs = useMemo(() => {
    if (catFilter !== 'all' || jobSearch) return null;
    const order = ['retail', 'lager', 'verkauf', 'gastro', 'quereinstieg'];
    const groups = {};
    filteredJobs.forEach(job => {
      const k = job.category || 'other';
      if (!groups[k]) groups[k] = [];
      groups[k].push(job);
    });
    const sorted = order.filter(k => groups[k]?.length);
    const rest = Object.keys(groups).filter(k => !order.includes(k) && groups[k]?.length);
    return [...sorted, ...rest].map(k => ({ key: k, jobs: groups[k] }));
  }, [filteredJobs, catFilter, jobSearch]);

  if (!user) return (
    <div className="login-page">
      <p style={{ color: 'var(--text-2)', fontStyle: 'italic' }}>Lade…</p>
    </div>
  );

  const showJobs = jobsList !== null;

  return (
    <div className="app">

      {/* ── Profile editor modal ─────────────── */}
      {editProfile && (
        <ProfileEditor
          profile={user.profile}
          onSave={handleProfileSaved}
          onClose={() => setEditProfile(false)}
        />
      )}

      {/* ── Header ─────────────────────────────── */}
      <header className="site-header">
        <div className="header-inner">
          <p className="header-eyebrow">Jobsuche &middot; Detailhandel &amp; mehr</p>
          <h1>Deine <em>passenden</em><br />Stellen</h1>
          <div className="header-meta">
            <div className="meta-stat">
              <strong>{user.profile.min_workload}%</strong>
              <span>Min. Pensum</span>
            </div>
            <div className="meta-divider" />
            <div className="meta-stat">
              <strong>{user.profile.interests?.length || 0}</strong>
              <span>Interessen</span>
            </div>
            <div className="meta-divider" />
            <div className="meta-stat">
              <strong>{user.profile.education_level || '—'}</strong>
              <span>Abschluss</span>
            </div>
          </div>
        </div>
        <div className="header-actions">
          <span className="user-greeting">Hallo, <strong>{user.username}</strong></span>
          <button className="icon-btn" onClick={toggleTheme} title="Theme wechseln">
            {isDark ? '☀' : '☽'}
          </button>
          <button className="logout-btn" onClick={handleLogout}>Abmelden</button>
        </div>
      </header>

      {/* ── Stats strip ────────────────────────── */}
      {results && !scraping && (
        <div className="stats-strip">
          <div className="strip-stat">
            <span className="strip-stat-num">{results.kept}</span>
            <span>Passende Stellen</span>
          </div>
          <div className="strip-stat">
            <span className="strip-stat-num">{results.easy_count ?? '—'}</span>
            <span>Easy Apply möglich</span>
          </div>
          <div className="strip-stat">
            <span className="strip-stat-num">{results.total}</span>
            <span>Geprüft</span>
          </div>
        </div>
      )}

      {/* ── Tab / filter bar ───────────────────── */}
      <div className="tab-bar">
        {!showJobs && (
          <>
            <button
              className={`tab-btn${activeTab === 'scrape' ? ' active' : ''}`}
              onClick={() => setActiveTab('scrape')}
            >
              Neue Suche
            </button>
            <button
              className={`tab-btn${activeTab === 'history' ? ' active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              Verlauf
            </button>
          </>
        )}

        {showJobs && (
          <>
            <span className="filter-label">Filter:</span>
            {CATEGORIES.map(({ key, label, icon }) => (
              <button
                key={key}
                className={`cat-btn${catFilter === key ? ' active' : ''}`}
                onClick={() => setCatFilter(key)}
              >
                {icon && <>{icon} </>}{key === 'all' ? 'Alle' : label}
              </button>
            ))}
            <div className="search-wrap">
              <span className="search-icon">🔍</span>
              <input
                className="search-input"
                type="text"
                placeholder="Suchen…"
                value={jobSearch}
                onChange={e => setJobSearch(e.target.value)}
              />
            </div>
            <button className="back-btn" onClick={() => setJobsList(null)}>← Zurück</button>
          </>
        )}
      </div>

      {/* ── Main content ───────────────────────── */}
      <main className="main-content">

        {/* Scrape panel */}
        {activeTab === 'scrape' && !showJobs && (
          <div className="scrape-panel">
            {/* Profile sidebar */}
            <aside className="profile-card">
              <p className="profile-title">Dein Profil</p>
              <div className="profile-rows">
                <div className="profile-row">
                  <span className="profile-key">Abschluss</span>
                  <span className="profile-val">{user.profile.education_level || '—'}</span>
                </div>
                <div className="profile-row">
                  <span className="profile-key">Min. Pensum</span>
                  <span className="profile-val">{user.profile.min_workload}%</span>
                </div>
                <div className="profile-row">
                  <span className="profile-key">Quereinstieg</span>
                  <span className="profile-val">{user.profile.allow_quereinstieg ? 'Ja' : 'Nein'}</span>
                </div>
              </div>
              {user.profile.interests?.length > 0 && (
                <div className="profile-interests">
                  <span className="profile-key">Interessen</span>
                  <div className="interest-tags">
                    {user.profile.interests.map((i, idx) => (
                      <span key={idx} className="interest-tag">{i}</span>
                    ))}
                  </div>
                </div>
              )}
              <button className="edit-profile-btn" onClick={() => setEditProfile(true)}>
                ✏ Profil bearbeiten
              </button>
            </aside>

            {/* Form + status */}
            <div className="scrape-right">
              <div className="scrape-form-card">
                <h3 className="card-heading">Suche starten</h3>
                <div className="form-row">
                  <input
                    className="location-input"
                    type="text"
                    value={location}
                    onChange={e => setLocation(e.target.value)}
                    placeholder="Ort (z.B. Winterthur)"
                    disabled={scraping}
                  />
                  <input
                    className="pages-input"
                    type="number"
                    value={maxPages}
                    onChange={e => setMaxPages(e.target.value)}
                    placeholder="Max. Seiten"
                    disabled={scraping}
                  />
                </div>
                <button
                  className={`scrape-btn${scraping ? ' loading' : ''}`}
                  onClick={handleScrape}
                  disabled={scraping}
                >
                  {scraping ? 'Läuft…' : 'Jobs suchen →'}
                </button>
              </div>

              {(scraping || results) && (
                <div className="status-card">
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${progress}%` }} />
                  </div>
                  <p className="status-msg">{statusMsg}</p>

                  {results && !scraping && (
                    <div className="results-summary">
                      <div className="result-stat">
                        <strong>{results.total}</strong>
                        <span>Geprüft</span>
                      </div>
                      <div className="result-stat highlight">
                        <strong>{results.kept}</strong>
                        <span>Passend</span>
                      </div>
                      <button className="view-jobs-btn" onClick={() => fetchJobs(results.search_id)}>
                        Jobs ansehen →
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* History */}
        {activeTab === 'history' && !showJobs && (
          <div className="history-card">
            <p className="section-heading">Suchverlauf</p>
            {history.length === 0 ? (
              <p className="empty-msg">Noch keine Suchen gespeichert.</p>
            ) : (
              <table className="history-table">
                <thead>
                  <tr>
                    <th>Datum</th>
                    <th>Ort</th>
                    <th>Geprüft / Passend</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {history.map(item => {
                    const d = new Date(item.timestamp);
                    return (
                      <tr key={item.id}>
                        <td>
                          {d.toLocaleDateString('de-CH')}{' '}
                          {d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td className="capitalize">{item.location}</td>
                        <td>
                          {item.summary.total} /{' '}
                          <strong className="kept-count">{item.summary.kept}</strong>
                        </td>
                        <td>
                          <button className="view-btn" onClick={() => fetchJobs(item.id)}>
                            Ansehen
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Jobs list */}
        {showJobs && (
          <div className="jobs-section">
            {statusMsg === 'Lade Jobs…' ? (
              <p className="loading-msg">Lade Jobs…</p>
            ) : (
              <>
                <div className="jobs-count">
                  <span className="jobs-count-num">{filteredJobs.length}</span>
                  <span className="jobs-count-label">
                    Stelle{filteredJobs.length !== 1 ? 'n' : ''}
                    {(catFilter !== 'all' || jobSearch) ? ' (gefiltert)' : ''}
                  </span>
                </div>

                {groupedJobs ? (
                  groupedJobs.length === 0 ? (
                    <p className="empty-grid">Keine Stellen gefunden.</p>
                  ) : (
                    groupedJobs.map(({ key, jobs }) => (
                      <CategorySection key={key} catKey={key} jobs={jobs} />
                    ))
                  )
                ) : (
                  <div className="jobs-grid">
                    {filteredJobs.map((job, idx) => (
                      <JobCard key={job.uuid || idx} job={job} idx={idx} />
                    ))}
                    {filteredJobs.length === 0 && (
                      <p className="empty-grid">Keine Stellen gefunden.</p>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </main>

      {/* ── Footer ─────────────────────────────── */}
      <footer className="site-footer">
        <span className="footer-logo">Stellen.</span>
        <span className="footer-note">
          Gefiltert aus jobs.ch &middot; {user.username}
        </span>
      </footer>
    </div>
  );
}
