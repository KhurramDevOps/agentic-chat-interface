import React from 'react';
import '../../styles/Chat.css';

/**
 * StreamingDot
 * ─────────────
 * Animated three-dot indicator shown while the AI is generating a response.
 */
function StreamingDot() {
  return (
    <div className="streaming-dot-wrapper">
      <span className="streaming-dot" />
      <span className="streaming-dot" />
      <span className="streaming-dot" />
    </div>
  );
}

export default StreamingDot;
