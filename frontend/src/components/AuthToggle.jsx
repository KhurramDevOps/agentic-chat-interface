import React from 'react';
import '../styles/AuthPortal.css';

export default function AuthToggle({ isLogin, onToggle }) {
  return (
    <p className="auth-toggle-text">
      {isLogin ? "Don't have an account?" : 'Already have an account?'}{' '}
      <button type="button" className="auth-toggle-btn" onClick={onToggle}>
        {isLogin ? 'Register' : 'Sign In'}
      </button>
    </p>
  );
}
