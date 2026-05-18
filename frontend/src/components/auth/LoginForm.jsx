import React, { useState } from 'react';
import LoadingSpinner from '../ui/LoadingSpinner';
import { useAuth } from '../../hooks/useAuth';

export default function LoginForm() {
  const { error, isLoading, login, setError } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState({ email: '', password: '' });

  const updateField = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    await login(form);
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="mb-4">
        <p className="text-accent mb-2">Secure access</p>
        <h2 className="gradient-text mb-2">Welcome back</h2>
        <p className="text-secondary mb-0">Sign in to resume your agentic workspace.</p>
      </div>
      {error ? <div className="alert alert-danger glass-card-sm">{error}</div> : null}
      <div className="mb-3">
        <label className="form-label text-secondary" htmlFor="login-email">Email</label>
        <input
          autoComplete="email"
          className="form-control form-control-lg"
          id="login-email"
          name="email"
          onChange={updateField}
          required
          type="email"
          value={form.email}
        />
      </div>
      <div className="mb-4">
        <label className="form-label text-secondary" htmlFor="login-password">Password</label>
        <div className="input-group">
          <input
            autoComplete="current-password"
            className="form-control form-control-lg"
            id="login-password"
            name="password"
            onChange={updateField}
            required
            type={showPassword ? 'text' : 'password'}
            value={form.password}
          />
          <button
            className="btn btn-nexus-ghost"
            onClick={() => setShowPassword((value) => !value)}
            title={showPassword ? 'Hide password' : 'Show password'}
            type="button"
          >
            <i className={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} />
          </button>
        </div>
      </div>
      <button className="btn btn-nexus-primary w-100" disabled={isLoading} type="submit">
        {isLoading ? <LoadingSpinner size="sm" /> : 'Enter Nexus'}
      </button>
    </form>
  );
}
