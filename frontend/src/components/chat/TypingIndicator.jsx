import React from 'react';

export default function TypingIndicator() {
  return (
    <div className="message-row assistant">
      <span className="nexus-avatar">N</span>
      <div className="message-bubble assistant glass-card-sm">
        <div className="typing-dots" aria-label="Nexus is typing">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  );
}
