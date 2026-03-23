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

  const handleScrape = () => {
    setScraping(true);
    setProgress(2);
    setStatusMsg('Waking up the scraper...');
    setResults(null);

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
      setResults(d.stats);
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
    <div style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
        <h1 style={{ margin: 0, fontSize: '2rem' }}>JobScraper Dashboard</h1>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <span>Welcome, <strong>{user.username}</strong></span>
          <button onClick={toggleTheme} style={{ padding: '0.5rem', cursor: 'pointer', background: 'var(--sand)', border: '1px solid var(--border-color)', borderRadius: '4px' }}>Toggle Theme</button>
          <button onClick={handleLogout} style={{ padding: '0.5rem 1rem', cursor: 'pointer', background: 'var(--rust)', color: 'white', border: 'none', borderRadius: '4px' }}>Logout</button>
        </div>
      </header>

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
                      <button style={{ marginTop: '1rem', padding: '0.5rem 1rem', background: 'var(--ink)', color: 'var(--cream)', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                          View Jobs
                      </button>
                  </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
