import React, { useEffect } from 'react';

export default function ErrorToast({ message, onClose }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div className="error-toast glass-card p-3">
      <div className="d-flex align-items-start gap-3">
        <i className="bi bi-exclamation-triangle-fill text-danger fs-5" />
        <div className="flex-grow-1">
          <strong className="d-block">Request failed</strong>
          <span className="text-secondary">{message}</span>
        </div>
        <button className="btn btn-sm btn-nexus-ghost" onClick={onClose} type="button" aria-label="Close">
          <i className="bi bi-x" />
        </button>
      </div>
    </div>
  );
}
