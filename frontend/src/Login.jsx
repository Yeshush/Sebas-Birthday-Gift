import { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const res = await axios.post('/api/login', { username, password });
      localStorage.setItem('token', res.data.access_token);
      navigate('/dashboard');
    } catch {
      setError('Benutzername oder Passwort falsch.');
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <p className="login-eyebrow">jobs.ch &middot; Dein persönlicher Filter</p>
          <h1>Stellen<em>.</em></h1>
        </div>

        {error && <p className="login-error">{error}</p>}

        <form className="login-form" onSubmit={handleLogin}>
          <div className="field-group">
            <label className="field-label" htmlFor="u">Benutzername</label>
            <input
              id="u"
              className="field-input"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
            />
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="p">Passwort</label>
            <input
              id="p"
              className="field-input"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <button className="login-btn" type="submit">Einloggen →</button>
        </form>
      </div>
    </div>
  );
}
