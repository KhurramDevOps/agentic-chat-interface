import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';

export default function SignIn() {
  const navigate = useNavigate();
  useEffect(() => {
    document.title = 'Nexus AI';
  }, []);
  const [form, setForm] = useState({ email: '', password: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const updateField = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError('');
  };

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await api.post('/auth/login', form);
      localStorage.setItem('nexus_token', response.data.token);
      localStorage.setItem('nexus_user', JSON.stringify(response.data.user || {}));
      navigate(response.data.user?.onboardingComplete || response.data.user?.onboardingCompleted ? '/chat' : '/onboarding');
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
      <form className="glass-card p-4 p-md-5 position-relative" onSubmit={submit} style={{ maxWidth: 520, width: '100%' }}>
        <div className="d-flex gap-2 mb-4">
          <button className="btn btn-nexus-primary flex-fill" type="button" onClick={() => navigate('/auth/signin')}>Sign In</button>
          <button className="btn btn-nexus-ghost flex-fill" type="button" onClick={() => navigate('/auth/register')}>Register</button>
        </div>
        <h1 className="gradient-text h2 mb-2">Welcome back</h1>
        <p className="text-secondary mb-4">Sign in to stream with Nexus.</p>
        {error ? <div className="alert alert-danger">{error}</div> : null}
        <label className="form-label text-secondary" htmlFor="signin-email">Email</label>
        <input id="signin-email" name="email" className="form-control form-control-lg mb-3" type="email" value={form.email} onChange={updateField} required />
        <label className="form-label text-secondary" htmlFor="signin-password">Password</label>
        <div className="password-field mb-4">
          <input id="signin-password" name="password" className="form-control form-control-lg" type={showPassword ? 'text' : 'password'} value={form.password} onChange={updateField} required />
          <button aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)} type="button">
            {showPassword ? '◉' : '◌'}
          </button>
        </div>
        <button className="btn btn-nexus-primary w-100" disabled={loading} type="submit">
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </main>
  );
}
