import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';

export default function Register() {
  const navigate = useNavigate();
  useEffect(() => {
    document.title = 'Nexus AI';
  }, []);
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '' });
  const [visible, setVisible] = useState({ password: false, confirmPassword: false });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const updateField = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError('');
  };

  const submit = async (event) => {
    event.preventDefault();
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/auth/register', {
        name: form.name,
        email: form.email,
        password: form.password,
      });
      localStorage.setItem('nexus_token', response.data.token);
      localStorage.setItem('nexus_user', JSON.stringify(response.data.user || {}));
      navigate('/onboarding');
    } catch (err) {
      setError(
        err.response?.data?.message ||
        err.message ||
        'Could not reach the gateway on port 5001'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page d-flex align-items-center justify-content-center p-4">
      <div className="auth-mesh" />
      <form className="glass-card p-4 p-md-5 position-relative" onSubmit={submit} style={{ maxWidth: 560, width: '100%' }}>
        <div className="d-flex gap-2 mb-4">
          <button className="btn btn-nexus-ghost flex-fill" type="button" onClick={() => navigate('/auth/signin')}>Sign In</button>
          <button className="btn btn-nexus-primary flex-fill" type="button" onClick={() => navigate('/auth/register')}>Register</button>
        </div>
        <h1 className="gradient-text h2 mb-2">Create account</h1>
        <p className="text-secondary mb-4">Register to open your Nexus command channel.</p>
        {error ? <div className="alert alert-danger">{error}</div> : null}
        <label className="form-label text-secondary" htmlFor="register-name">Name</label>
        <input id="register-name" name="name" className="form-control form-control-lg mb-3" value={form.name} onChange={updateField} required />
        <label className="form-label text-secondary" htmlFor="register-email">Email</label>
        <input id="register-email" name="email" className="form-control form-control-lg mb-3" type="email" value={form.email} onChange={updateField} required />
        <div className="row">
          <div className="col-md-6">
            <label className="form-label text-secondary" htmlFor="register-password">Password</label>
            <div className="password-field mb-3">
              <input id="register-password" name="password" className="form-control form-control-lg" type={visible.password ? 'text' : 'password'} value={form.password} onChange={updateField} required />
              <button aria-label={visible.password ? 'Hide password' : 'Show password'} onClick={() => setVisible((state) => ({ ...state, password: !state.password }))} type="button">
                {visible.password ? '◉' : '◌'}
              </button>
            </div>
          </div>
          <div className="col-md-6">
            <label className="form-label text-secondary" htmlFor="register-confirm">Confirm Password</label>
            <div className="password-field mb-4">
              <input id="register-confirm" name="confirmPassword" className="form-control form-control-lg" type={visible.confirmPassword ? 'text' : 'password'} value={form.confirmPassword} onChange={updateField} required />
              <button aria-label={visible.confirmPassword ? 'Hide password' : 'Show password'} onClick={() => setVisible((state) => ({ ...state, confirmPassword: !state.confirmPassword }))} type="button">
                {visible.confirmPassword ? '◉' : '◌'}
              </button>
            </div>
          </div>
        </div>
        <button className="btn btn-nexus-primary w-100" disabled={loading} type="submit">
          {loading ? 'Registering...' : 'Register'}
        </button>
      </form>
    </main>
  );
}
