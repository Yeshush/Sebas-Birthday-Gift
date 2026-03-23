import { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

export default function Dashboard() {
  const [user, setUser] = useState(null);
  const [location, setLocation] = useState('winterthur');
  const [maxPages, setMaxPages] = useState('');
  const [scraping, setScraping] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [results, setResults] = useState(null);
  const [activeTab, setActiveTab] = useState('scrape'); // 'scrape' or 'history'
  const [history, setHistory] = useState([]);
  const [jobsList, setJobsList] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) throw new Error('No token');
        
        const res = await axios.get('/api/me', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setUser(res.data);
      } catch (err) {
        navigate('/');
      }
    };
    fetchUser();
  }, [navigate]);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab]);

  const fetchHistory = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/history', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setHistory(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchJobs = async (searchId) => {
    try {
      setStatusMsg('Loading jobs...');
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/history/${searchId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setJobsList(res.data.results);
      setStatusMsg('');
    } catch (err) {
      console.error(err);
      setStatusMsg('Failed to load jobs.');
    }
  };

  const handleScrape = () => {
    setScraping(true);
    setProgress(2);
    setStatusMsg('Waking up the scraper...');
    setResults(null);
    setJobsList(null);

    const token = localStorage.getItem('token');
    const url = `/scrape?location=${encodeURIComponent(location)}${maxPages ? `&max_pages=${maxPages}` : ''}&token=${token}`;
    
    const sse = new EventSource(url);

    sse.addEventListener('found', (e) => {
      const d = JSON.parse(e.data);
      setProgress(10);
      setStatusMsg(`Found ${d.total} jobs on ${d.total_pages} pages.`);
    });

    sse.addEventListener('page', (e) => {
      const d = JSON.parse(e.data);
      setProgress(d.progress);
      setStatusMsg(`Scraping page ${d.page} of ${d.total_pages}...`);
    });

    sse.addEventListener('stage', (e) => {
      const d = JSON.parse(e.data);
      setProgress(d.progress);
      setStatusMsg(`Filtering: ${d.stage} (${d.remaining} left)`);
    });

    sse.addEventListener('done', (e) => {
      const d = JSON.parse(e.data);
      setProgress(100);
      setStatusMsg('Done!');
      setResults({ ...d.stats, search_id: d.search_id });
      setScraping(false);
      sse.close();
    });

    sse.addEventListener('error_msg', (e) => {
      const d = JSON.parse(e.data);
      setStatusMsg(`Error: ${d.msg}`);
      setScraping(false);
      sse.close();
    });

    sse.onerror = () => {
      sse.close();
      if(scraping) {
          setScraping(false);
      }
    };
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/');
  };

  const toggleTheme = () => {
    document.body.classList.toggle('dark-mode');
  };

  if (!user) return <div style={{ padding: '2rem' }}>Loading...</div>;

  return (
    <div style={{ padding: '2rem', maxWidth: '1000px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
        <h1 style={{ margin: 0, fontSize: '2rem' }}>JobScraper</h1>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <span>Welcome, <strong>{user.username}</strong></span>
          <button onClick={toggleTheme} style={{ padding: '0.5rem', cursor: 'pointer', background: 'var(--sand)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'black' }}>Toggle Theme</button>
          <button onClick={handleLogout} style={{ padding: '0.5rem 1rem', cursor: 'pointer', background: 'var(--rust)', color: 'white', border: 'none', borderRadius: '4px' }}>Logout</button>
        </div>
      </header>

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
        <button 
          onClick={() => { setActiveTab('scrape'); setJobsList(null); }}
          style={{ padding: '0.5rem 1rem', background: activeTab === 'scrape' ? 'var(--ink)' : 'transparent', color: activeTab === 'scrape' ? 'var(--cream)' : 'inherit', border: '1px solid var(--border-color)', borderRadius: '4px', cursor: 'pointer' }}>
          New Search
        </button>
        <button 
          onClick={() => { setActiveTab('history'); setJobsList(null); }}
          style={{ padding: '0.5rem 1rem', background: activeTab === 'history' ? 'var(--ink)' : 'transparent', color: activeTab === 'history' ? 'var(--cream)' : 'inherit', border: '1px solid var(--border-color)', borderRadius: '4px', cursor: 'pointer' }}>
          History
        </button>
      </div>

      {activeTab === 'scrape' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '2rem' }}>
          <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--border-color)', height: 'fit-content' }}>
            <h3 style={{ marginTop: 0, marginBottom: '1.5rem' }}>Your Profile</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.9rem' }}>
              <div><strong>Education:</strong> {user.profile.education_level || 'Not set'}</div>
              <div><strong>Min Workload:</strong> {user.profile.min_workload}%</div>
              <div><strong>Quereinstieg:</strong> {user.profile.allow_quereinstieg ? 'Yes' : 'No'}</div>
              <div>
                  <strong>Interests:</strong>
                  <ul style={{ paddingLeft: '1.2rem', margin: '0.5rem 0 0 0' }}>
                      {user.profile.interests.map((i, idx) => <li key={idx}>{i}</li>)}
                  </ul>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <h3 style={{ marginTop: 0, marginBottom: '1rem' }}>Start Search</h3>
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                <input 
                  type="text" 
                  value={location} 
                  onChange={(e) => setLocation(e.target.value)} 
                  placeholder="Location (e.g. winterthur)" 
                  style={{ flex: 1, padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  disabled={scraping}
                />
                <input 
                  type="number" 
                  value={maxPages} 
                  onChange={(e) => setMaxPages(e.target.value)} 
                  placeholder="Max pages (opt)" 
                  style={{ width: '120px', padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  disabled={scraping}
                />
              </div>
              <button 
                onClick={handleScrape} 
                disabled={scraping}
                style={{ width: '100%', padding: '0.8rem', background: scraping ? 'var(--mist)' : 'var(--ink)', color: 'var(--cream)', border: 'none', borderRadius: '4px', cursor: scraping ? 'default' : 'pointer', fontWeight: 'bold' }}
              >
                {scraping ? 'Scraping in progress...' : 'Search Jobs'}
              </button>
            </div>

            {(scraping || results) && (
              <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <h3 style={{ marginTop: 0, marginBottom: '1rem' }}>Status</h3>
                
                <div style={{ height: '24px', background: 'var(--sand)', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border-color)', marginBottom: '1rem' }}>
                  <div style={{ height: '100%', width: `${progress}%`, background: 'var(--rust)', transition: 'width 0.3s' }}></div>
                </div>
                
                <p style={{ margin: 0, fontStyle: 'italic', color: 'var(--text-secondary)' }}>{statusMsg}</p>

                {results && !scraping && (
                    <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-color)' }}>
                        <h4 style={{ marginTop: 0 }}>Results</h4>
                        <p style={{ margin: '0.5rem 0' }}>Total Checked: <strong>{results.total}</strong></p>
                        <p style={{ margin: '0.5rem 0' }}>Matched Profile: <strong style={{ color: 'var(--rust)' }}>{results.kept}</strong></p>
                        <button 
                          onClick={() => fetchJobs(results.search_id)}
                          style={{ marginTop: '1rem', padding: '0.5rem 1rem', background: 'var(--ink)', color: 'var(--cream)', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                            View Jobs
                        </button>
                    </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'history' && !jobsList && (
        <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <h3 style={{ marginTop: 0, marginBottom: '1.5rem' }}>Search History</h3>
          {history.length === 0 ? (
            <p>No past searches found.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                  <th style={{ padding: '0.5rem' }}>Date</th>
                  <th style={{ padding: '0.5rem' }}>Location</th>
                  <th style={{ padding: '0.5rem' }}>Found / Kept</th>
                  <th style={{ padding: '0.5rem' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {history.map(item => {
                  const d = new Date(item.timestamp);
                  return (
                    <tr key={item.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.5rem' }}>{d.toLocaleDateString()} {d.toLocaleTimeString()}</td>
                      <td style={{ padding: '0.5rem' }}>{item.location}</td>
                      <td style={{ padding: '0.5rem' }}>{item.summary.total} / <strong style={{color: 'var(--rust)'}}>{item.summary.kept}</strong></td>
                      <td style={{ padding: '0.5rem' }}>
                        <button 
                          onClick={() => fetchJobs(item.id)}
                          style={{ padding: '0.3rem 0.8rem', background: 'var(--ink)', color: 'var(--cream)', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                          View
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {jobsList && (
        <div style={{ marginTop: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0 }}>Job Results ({jobsList.length})</h2>
            <button 
              onClick={() => setJobsList(null)}
              style={{ padding: '0.5rem 1rem', background: 'var(--mist)', color: 'var(--ink)', border: '1px solid var(--border-color)', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
              Back
            </button>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {jobsList.map((job, idx) => (
              <div key={idx} style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--ink)' }}>{job.title}</h3>
                    <p style={{ margin: '0 0 1rem 0', fontWeight: 'bold', color: 'var(--text-secondary)' }}>{job.company}</p>
                  </div>
                  {job.easy_apply && (
                    <span style={{ background: '#dcfce7', color: '#166534', padding: '0.3rem 0.6rem', borderRadius: '999px', fontSize: '0.8rem', fontWeight: 'bold' }}>
                      Easy Apply
                    </span>
                  )}
                </div>
                
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', fontSize: '0.9rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
                  {job.location && <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem' }}>📍 {job.location}</span>}
                  {job.workload && <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem' }}>⏱ {job.workload}</span>}
                  {job.date && <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem' }}>📅 {job.date}</span>}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <a 
                    href={job.link} 
                    target="_blank" 
                    rel="noreferrer" 
                    style={{ textDecoration: 'none', background: 'var(--rust)', color: 'white', padding: '0.6rem 1.2rem', borderRadius: '4px', fontWeight: 'bold', fontSize: '0.9rem' }}
                  >
                    View on Job-Room
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
