import React from 'react';
import '../../styles/Chat.css';

/**
 * MessageBubble
 * ──────────────
 * Renders a single chat message.
 * Applies .bubble-user or .bubble-assistant CSS class based on role.
 */
function MessageBubble({ role, content }) {
  const isUser = role === 'user';

  return (
    <div className={`bubble-wrapper ${isUser ? 'bubble-wrapper--user' : 'bubble-wrapper--assistant'}`}>
      <div className={isUser ? 'bubble-user' : 'bubble-assistant'}>
        {content}
      </div>
    </div>
  );
}

export default MessageBubble;
