import React from 'react';
import '../styles/AuthPortal.css';

export default function AuthCard({ children }) {
  return (
    <div className="auth-card">
      {children}
    </div>
  );
}
