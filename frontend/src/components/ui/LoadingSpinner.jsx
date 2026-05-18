import React from 'react';

export default function LoadingSpinner({ fullscreen = false, size = 'md' }) {
  const ring = <span className="spinner-ring d-inline-block" style={size === 'sm' ? { height: 18, width: 18, borderWidth: 2 } : undefined} />;

  if (fullscreen) {
    return <div className="spinner-fullscreen">{ring}</div>;
  }

  return ring;
}
