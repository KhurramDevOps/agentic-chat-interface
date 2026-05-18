import React, { createContext, useCallback, useState } from 'react';

export const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [activeSessionName, setActiveSessionName] = useState('New Chat');

  const startNewChat = useCallback(() => {
    setActiveSessionId(null);
    setActiveSessionName('New Chat');
  }, []);

  const selectSession = useCallback((session) => {
    setActiveSessionId(session.id || session._id || session.session_id);
    setActiveSessionName(session.name || session.title || 'Chat');
  }, []);

  return (
    <ChatContext.Provider
      value={{
        activeSessionId,
        setActiveSessionId,
        activeSessionName,
        setActiveSessionName,
        startNewChat,
        selectSession,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}
