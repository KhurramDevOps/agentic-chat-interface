import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ChatContext } from '../../context/ChatContext';
import { useAuth } from '../../hooks/useAuth';
import { useHistory, useSendMessage } from '../../hooks/useChat';
import ErrorToast from '../ui/ErrorToast';
import MessageBubble from './MessageBubble';
import MessageInput from './MessageInput';
import TypingIndicator from './TypingIndicator';

export default function ChatWindow() {
  const bottomRef = useRef(null);
  const { user } = useAuth();
  const { activeSessionId } = useContext(ChatContext);
  const history = useHistory(activeSessionId);
  const sendMessage = useSendMessage();
  const [optimisticMessages, setOptimisticMessages] = useState([]);
  const [error, setError] = useState('');

  const welcomeMessage = useMemo(() => {
    const displayName = localStorage.getItem('nexus_display_name') || user?.name || 'there';
    return {
      role: 'assistant',
      content: `Hello ${displayName} 👋 I'm **Nexus**, your agentic AI assistant. I can search the web, generate images, answer complex questions, and help with files. What would you like to explore today?`,
      isWelcome: true,
      createdAt: new Date().toISOString(),
    };
  }, [user?.name]);

  const persistedMessages = activeSessionId ? history.data || [] : [welcomeMessage];
  const messages = [...persistedMessages, ...optimisticMessages];

  useEffect(() => {
    setOptimisticMessages([]);
  }, [activeSessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, sendMessage.isPending]);

  const handleSend = async (content) => {
    const userMessage = { role: 'user', content, createdAt: new Date().toISOString(), optimistic: true };
    setOptimisticMessages((current) => [...current, userMessage]);
    try {
      const response = await sendMessage.mutateAsync({ message: content, session_id: activeSessionId });
      const assistantContent = response.response || response.message || response.content || '';
      setOptimisticMessages((current) => [
        ...current.filter((message) => message !== userMessage),
        userMessage,
        { role: 'assistant', content: assistantContent, createdAt: new Date().toISOString(), optimistic: true },
      ]);
    } catch (err) {
      setOptimisticMessages((current) => current.filter((message) => message !== userMessage));
      setError(err.response?.data?.error || err.response?.data?.detail || err.message || 'Nexus could not complete the request.');
    }
  };

  return (
    <section className="chat-window">
      <header className="glass-card-sm p-3 mb-3 d-flex align-items-center justify-content-between">
        <div>
          <h1 className="h5 mb-1 gradient-text">Nexus Command Channel</h1>
          <span className="text-secondary small">{activeSessionId ? `Session ${activeSessionId}` : 'New secure chat'}</span>
        </div>
        <span className="badge rounded-pill text-bg-primary">Gateway 5001</span>
      </header>
      <div className="message-list flex-grow-1 pe-2">
        {history.isLoading ? <div className="skeleton mb-3" style={{ height: 120 }} /> : null}
        {messages.map((message, index) => (
          <MessageBubble key={`${message.createdAt}-${index}`} message={message} />
        ))}
        {sendMessage.isPending ? <TypingIndicator /> : null}
        <div ref={bottomRef} />
      </div>
      <div className="pt-3">
        <MessageInput disabled={sendMessage.isPending} onSend={handleSend} />
      </div>
      <ErrorToast message={error} onClose={() => setError('')} />
    </section>
  );
}
