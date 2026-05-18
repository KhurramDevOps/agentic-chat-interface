import React from 'react';
import '../../styles/AuthPortal.css';

export default function AuthHeader({ isLogin }) {
  return (
    <div>
      <h1 className="auth-header-title">
        {isLogin ? 'Sign In' : 'Create Account'}
      </h1>
      <p className="auth-header-subtitle">
        {isLogin
          ? 'Welcome back. Enter your credentials.'
          : 'Fill in the details below to register.'}
      </p>
    </div>
  );
}
