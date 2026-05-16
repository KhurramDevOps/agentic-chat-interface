import React, { useState } from 'react';
import useChatStore from '../../store/chatStore';
import useAuthStore from '../../store/authStore';
import '../../styles/Chat.css';

/**
 * InputArea
 * ──────────
 * Controlled textarea for composing messages.
 *
 * On Enter (without Shift):
 *   1. Commits the user message to chatStore.
 *   2. Calls sendMessage(payload) via the WebSocket hook.
 *   3. Clears the input.
 *
 * Disabled while isStreaming === true.
 */
function InputArea({ sendMessage, sessionId }) {
  const [text, setText] = useState('');

  const addMessage = useChatStore((s) => s.addMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const user = useAuthStore((s) => s.user);

  const handleSend = () => {
    const content = text.trim();
    if (!content || isStreaming) return;

    // 1. Commit user message to store
    addMessage('user', content);

    // 2. Build and send WebSocket payload
    const payload = {
      request_id: crypto.randomUUID(),
      messages: [{ role: 'user', content }],
      model: 'gemini/gemini-1.5-pro',
      memory_context_id: sessionId,
      user_id: user?._id || user?.id || sessionId, // Issue 3: Mem0 user key
    };
    sendMessage(payload);

    // 3. Clear input
    setText('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="input-area">
      <textarea
        className="input-textarea"
        rows={3}
        placeholder={isStreaming ? 'AI is responding...' : 'Type a message... (Enter to send)'}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isStreaming}
      />
      <button
        className="input-send-btn"
        onClick={handleSend}
        disabled={isStreaming || !text.trim()}
      >
        Send
      </button>
    </div>
  );
}

export default InputArea;
