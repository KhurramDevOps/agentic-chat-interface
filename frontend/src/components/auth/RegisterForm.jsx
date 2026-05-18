import React, { useState } from 'react';
import LoadingSpinner from '../ui/LoadingSpinner';
import { useAuth } from '../../hooks/useAuth';

export default function RegisterForm({ onRegistered }) {
  const { error, isLoading, register, setError } = useAuth();
  const [localError, setLocalError] = useState('');
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '' });

  const updateField = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setLocalError('');
    setError(null);
  };

  const validate = () => {
    if (form.name.trim().length < 2) return 'Name must be at least 2 characters.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) return 'Use a valid email address.';
    if (form.password.length < 6) return 'Password must be at least 6 characters.';
    if (form.password !== form.confirmPassword) return 'Passwords do not match.';
    return '';
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setLocalError(validationError);
      return;
    }
    await register({ name: form.name.trim(), email: form.email.trim(), password: form.password });
    onRegistered();
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="mb-4">
        <p className="text-accent mb-2">Create command access</p>
        <h2 className="gradient-text mb-2">Launch Nexus</h2>
        <p className="text-secondary mb-0">Build your secure AI workspace in seconds.</p>
      </div>
      {error || localError ? <div className="alert alert-danger glass-card-sm">{error || localError}</div> : null}
      <div className="mb-3">
        <label className="form-label text-secondary" htmlFor="register-name">Name</label>
        <input className="form-control form-control-lg" id="register-name" name="name" onChange={updateField} required value={form.name} />
      </div>
      <div className="mb-3">
        <label className="form-label text-secondary" htmlFor="register-email">Email</label>
        <input className="form-control form-control-lg" id="register-email" name="email" onChange={updateField} required type="email" value={form.email} />
      </div>
      <div className="row">
        <div className="col-md-6 mb-4">
          <label className="form-label text-secondary" htmlFor="register-password">Password</label>
          <input className="form-control form-control-lg" id="register-password" name="password" onChange={updateField} required type="password" value={form.password} />
        </div>
        <div className="col-md-6 mb-4">
          <label className="form-label text-secondary" htmlFor="register-confirm">Confirm</label>
          <input className="form-control form-control-lg" id="register-confirm" name="confirmPassword" onChange={updateField} required type="password" value={form.confirmPassword} />
        </div>
      </div>
      <button className="btn btn-nexus-primary w-100" disabled={isLoading} type="submit">
        {isLoading ? <LoadingSpinner size="sm" /> : 'Create Account'}
      </button>
    </form>
  );
}
