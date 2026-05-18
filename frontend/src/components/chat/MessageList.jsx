import React, { useEffect, useRef } from 'react';
import useChatStore from '../../store/chatStore';
import MessageBubble from './MessageBubble';
import StreamingDot from './StreamingDot';
import '../../styles/Chat.css';

/**
 * MessageList
 * ────────────
 * Renders the full conversation history plus the live streaming bubble.
 * Auto-scrolls to the bottom whenever messages or streamingContent change.
 */
function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamingContent = useChatStore((s) => s.streamingContent);
  const error = useChatStore((s) => s.error);

  const bottomRef = useRef(null);

  // Auto-scroll to bottom on every update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  return (
    <div className="message-list">

      {/* Committed messages */}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
      ))}

      {/* Live streaming bubble — visible while AI is generating */}
      {isStreaming && (
        <div className="bubble-wrapper bubble-wrapper--assistant">
          <div className="bubble-assistant">
            {streamingContent || <StreamingDot />}
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="alert alert-danger mx-3 mt-2" role="alert">
          {error}
        </div>
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} />
    </div>
  );
}

export default MessageList;
