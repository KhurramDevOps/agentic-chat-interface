import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import config from '../../config';

const emptyMemory = {
  name: '',
  nickname: '',
  occupation: '',
  location: '',
  facts: [],
  interests: [],
  memoryEnabled: true,
  webSearchEnabled: true,
  lastUpdated: null,
};

const statusLabels = {
  thinking: 'thinking',
  searching: 'searching',
  reading: 'reading',
  retrieved: 'retrieved',
  processing: 'processing',
  done: 'done',
};

function getAuthHeaders() {
  const token = localStorage.getItem('nexus_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiJson(path, options = {}) {
  const response = await fetch(`${config.apiUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || 'Request failed');
  return data;
}

function groupSessions(sessions) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const lastWeek = new Date(today);
  lastWeek.setDate(lastWeek.getDate() - 7);

  return sessions.reduce((groups, session) => {
    const date = new Date(session.updatedAt || session.createdAt);
    let label = 'Older';
    if (date >= today) label = 'Today';
    else if (date >= yesterday) label = 'Yesterday';
    else if (date >= lastWeek) label = 'Last 7 days';
    groups[label] = [...(groups[label] || []), session];
    return groups;
  }, {});
}

function parseSseFrame(frame) {
  const lines = frame.split('\n');
  let event = 'message';
  const data = [];
  for (const line of lines) {
    if (line.startsWith('event: ')) event = line.slice(7).trim();
    if (line.startsWith('data: ')) data.push(line.slice(6));
  }
  return { event, data: data.join('\n') };
}

function parseTypedEvent(data) {
  try {
    const parsed = JSON.parse(data);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function initials(user) {
  const source = user?.name || user?.email || 'User';
  return source
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'U';
}

function formatTime(value) {
  if (!value) return '';
  return new Intl.DateTimeFormat([], { hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

function fileSize(size) {
  if (!size) return '0 KB';
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function domainFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url || 'source';
  }
}

function toPreview(file) {
  return {
    file,
    name: file.name,
    size: file.size,
    type: file.type,
    url: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
  };
}

function TypingDots() {
  return (
    <span className="typing-dots" aria-label="Nexus is typing">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </span>
  );
}

function ThinkingPanel({ collapsed, done, onToggle, steps }) {
  if (!steps.length) return null;
  return (
    <section className={`thinking-panel ${done ? 'done' : 'active'} ${collapsed ? 'collapsed' : ''}`}>
      <button className="thinking-header" onClick={onToggle} type="button">
        <span className={done ? 'thinking-spinner done' : 'thinking-spinner'} />
        <strong>{done ? '✓ Done' : '● Nexus is thinking...'}</strong>
        <em>{collapsed ? 'Expand' : 'Collapse'}</em>
      </button>
      {!collapsed ? (
        <div className="thinking-steps">
          {steps.map((step, index) => (
            <div className="thinking-step" key={`${step.id || step.text || step.label}-${index}`}>
              <i className={`status-dot ${step.status || 'thinking'}`} />
              <span>{step.icon || '✦'}</span>
              <p>{step.text || step.label}</p>
              <small>{step.elapsed || statusLabels[step.status] || step.status || 'thinking'}</small>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function AttachmentPreview({ attachments = [] }) {
  if (!attachments.length) return null;
  return (
    <div className="bubble-attachments">
      {attachments.map((attachment, index) => (
        attachment.type === 'image' ? (
          <img alt={attachment.name || 'upload'} key={`${attachment.name}-${index}`} src={attachment.url} />
        ) : (
          <div className="document-pill" key={`${attachment.name}-${index}`}>
            <span>📄</span>
            <strong>{attachment.name}</strong>
          </div>
        )
      ))}
    </div>
  );
}

function CodeBlock({ children, className }) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const language = match?.[1] || 'text';
  const code = String(children || '').replace(/\n$/, '');

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="code-block-shell">
      <div className="code-block-header">
        <span>{language}</span>
        <button onClick={copy} type="button">{copied ? 'Copied!' : 'Copy'}</button>
      </div>
      <SyntaxHighlighter
        className="code-block"
        customStyle={{ margin: 0, background: '#1e1e2e', fontSize: 13 }}
        language={language}
        PreTag="div"
        style={oneDark}
        wrapLongLines={false}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

function RenderedMessage({ content, isUser }) {
  if (isUser) {
    return <div className="message-content plain-text">{content}</div>;
  }

  return (
    <div className="markdown-content message-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => <a href={href} rel="noreferrer" target="_blank">{children}</a>,
          code: ({ inline, className, children, ...props }) => (
            inline || (!className && !String(children).includes('\n')) ? (
              <code className={className} {...props}>{children}</code>
            ) : (
              <CodeBlock className={className}>{children}</CodeBlock>
            )
          ),
        }}
      >
        {String(content || '')}
      </ReactMarkdown>
    </div>
  );
}

function MessageBubble({ copied, message, onCopy, onReact, user }) {
  const isUser = message.role === 'user';
  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser ? <span className="nexus-avatar">N</span> : null}
      <div className="message-stack">
        <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
          <AttachmentPreview attachments={message.attachments} />
          {message.streaming && !message.content ? <TypingDots /> : <RenderedMessage content={message.content} isUser={isUser} />}
          {!isUser ? (
            <div className="bubble-actions">
              <button onClick={() => onCopy(message)} type="button">{copied ? 'Copied!' : 'Copy'}</button>
              <button onClick={() => onReact(message, 'up')} type="button">👍</button>
              <button onClick={() => onReact(message, 'down')} type="button">👎</button>
            </div>
          ) : null}
        </div>
        <div className="message-meta">
          <span>{formatTime(message.createdAt)}</span>
          {isUser ? <span>{message.status === 'received' ? '✓✓ received' : '✓ sent'}</span> : null}
        </div>
        {!isUser && message.searchUsed && message.sources?.length ? (
          <div className="sources-row">
            <span>Sources:</span>
            {message.sources.map((source, index) => (
              <a href={source.url} key={`${source.url}-${index}`} rel="noopener noreferrer" target="_blank">
                {source.domain || domainFromUrl(source.url)}
              </a>
            ))}
          </div>
        ) : null}
      </div>
      {isUser ? <span className="user-message-avatar">{initials(user)}</span> : null}
    </div>
  );
}

export default function ChatPage() {
  const storedUser = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('nexus_user')) || {};
    } catch {
      return {};
    }
  }, []);

  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [activeTitle, setActiveTitle] = useState('New chat');
  const [messages, setMessages] = useState([]);
  const [memory, setMemory] = useState(emptyMemory);
  const [input, setInput] = useState('');
  const [files, setFiles] = useState([]);
  const [webSearch, setWebSearch] = useState(false);
  const [codeMode, setCodeMode] = useState(false);
  const [deepThink, setDeepThink] = useState(false);
  const [currentResponse, setCurrentResponse] = useState('');
  const [currentSources, setCurrentSources] = useState([]);
  const [currentSearchUsed, setCurrentSearchUsed] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState([]);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(false);
  const [thinkingDone, setThinkingDone] = useState(false);
  const [copiedId, setCopiedId] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [profileForm, setProfileForm] = useState({ name: storedUser.name || '', currentPassword: '', password: '', confirmPassword: '' });
  const [showProfilePasswords, setShowProfilePasswords] = useState({});
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const messagesRef = useRef(null);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const formRef = useRef(null);
  const pendingSuggestionRef = useRef('');

  const groupedSessions = useMemo(() => groupSessions(
    sessions.filter((session) => session.title.toLowerCase().includes(search.trim().toLowerCase()))
  ), [search, sessions]);

  const renderedMessages = useMemo(() => messages, [messages]);
  const hasMessages = renderedMessages.length > 0;

  const memoryCount = [
    memory.name,
    memory.location,
    memory.occupation,
    ...(memory.interests || []),
    ...(memory.facts || []),
  ].filter(Boolean).length;

  const loadSessions = async () => {
    const data = await apiJson('/api/chat/sessions');
    setSessions(data.sessions || []);
  };

  const loadMemory = async () => {
    const data = await apiJson('/api/chat/memory');
    setMemory({ ...emptyMemory, ...(data.memory || {}) });
    setWebSearch(false);
  };

  useEffect(() => {
    document.title = `${activeTitle || 'New chat'} — Nexus`;
  }, [activeTitle]);

  useEffect(() => {
    loadSessions().catch((err) => setError(err.message));
    loadMemory().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      setShowScrollButton(false);
    } else if (isStreaming || renderedMessages.length) {
      setShowScrollButton(true);
    }
  }, [renderedMessages, thinkingSteps, isStreaming, isNearBottom]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const startNewChat = () => {
    setActiveSessionId(null);
    setActiveTitle('New chat');
    setMessages([]);
    setCurrentResponse('');
    setThinkingSteps([]);
    setThinkingDone(false);
    setError('');
  };

  const loadSession = async (session) => {
    if (isStreaming) return;
    setError('');
    setActiveSessionId(session.id);
    setActiveTitle(session.title);
    const data = await apiJson(`/api/chat/history/${session.id}`);
    setMessages(data.messages || []);
    setThinkingSteps([]);
  };

  const clearMemory = async () => {
    if (!window.confirm('Clear long-term memory for this account?')) return;
    const data = await apiJson('/api/chat/memory', { method: 'DELETE' });
    setMemory({ ...emptyMemory, ...(data.memory || {}) });
  };

  const deleteFact = async (index) => {
    const data = await apiJson(`/api/users/memory/${index}`, { method: 'DELETE' });
    setMemory({ ...emptyMemory, ...(data.memory || {}) });
  };

  const logout = () => {
    setActiveSessionId(null);
    setMessages([]);
    localStorage.removeItem('nexus_token');
    localStorage.removeItem('nexus_user');
    window.location.assign('/');
  };

  const saveProfile = async (event) => {
    event.preventDefault();
    if (profileForm.password && profileForm.password !== profileForm.confirmPassword) {
      setError('New passwords do not match.');
      return;
    }
    const payload = {};
    if (profileForm.name.trim()) payload.name = profileForm.name.trim();
    if (profileForm.password) {
      payload.currentPassword = profileForm.currentPassword;
      payload.password = profileForm.password;
    }
    const data = await apiJson('/api/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    localStorage.setItem('nexus_user', JSON.stringify(data.user || storedUser));
    setProfileModalOpen(false);
  };

  const shareChat = async () => {
    const text = messages.map((message) => `${message.role}: ${message.content}`).join('\n\n');
    try {
      await navigator.clipboard.writeText(text || activeTitle);
      setError('');
    } catch {
      setError('Unable to copy chat to clipboard.');
    }
  };

  const onFilesSelected = (event) => {
    const selected = Array.from(event.target.files || []).filter((file) => file.type.startsWith('image/'));
    setFiles((current) => {
      const next = [...current];
      for (const file of selected) {
        if (next.length >= 3) break;
        next.push(toPreview(file));
      }
      return next.slice(0, 3);
    });
    event.target.value = '';
  };

  const removeFile = (index) => {
    setFiles((current) => {
      const next = [...current];
      if (next[index]?.url) URL.revokeObjectURL(next[index].url);
      next.splice(index, 1);
      return next;
    });
  };

  const copyMessage = async (message) => {
    await navigator.clipboard.writeText(message.content || '');
    setCopiedId(message.id || message.createdAt);
    setTimeout(() => setCopiedId(''), 1200);
  };

  const reactToMessage = async (message, reaction) => {
    if (!message.id) return;
    await apiJson(`/api/messages/${message.id}/reaction`, {
      method: 'POST',
      body: JSON.stringify({ reaction }),
    });
    setMessages((current) => current.map((item) => (
      item.id === message.id ? { ...item, reaction } : item
    )));
  };

  const sendMessage = async (event) => {
    event.preventDefault();
    const message = (pendingSuggestionRef.current || input).trim();
    pendingSuggestionRef.current = '';
    if ((!message && !files.length) || isStreaming) return;

    const optimisticAttachments = files.map((preview) => ({
      type: preview.type.startsWith('image/') ? 'image' : 'document',
      name: preview.name,
      mimeType: preview.type,
      size: preview.size,
      url: preview.url,
    }));
    const optimistic = {
      role: 'user',
      content: message || 'Uploaded file',
      attachments: optimisticAttachments,
      status: 'sent',
      createdAt: new Date().toISOString(),
    };
    const nextMessages = [...messages, optimistic];
    setMessages(nextMessages);
    if (!activeSessionId) setActiveTitle((message || files[0]?.name || 'New chat').slice(0, 64));
    setInput('');
    setFiles([]);
    setCurrentResponse('');
    setCurrentSources([]);
    setCurrentSearchUsed(false);
    setThinkingSteps([]);
    setThinkingCollapsed(false);
    setThinkingDone(false);
    setError('');
    setIsStreaming(true);

    let assistantText = '';
    let meta = null;
    let streamedSources = [];
    const streamStartedAt = performance.now();

    try {
      const formData = new FormData();
      formData.append('message', message || 'Please analyse and describe this image in detail.');
      if (activeSessionId) formData.append('conversationId', activeSessionId);
      formData.append('webSearch', String(webSearch));
      formData.append('codeMode', String(codeMode));
      formData.append('deepThink', String(deepThink));
      for (const preview of files) formData.append('images', preview.file);

      const response = await fetch(`${config.apiUrl}/api/chat`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });

      if (!response.ok || !response.body) throw new Error('AI stream failed to start.');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';

        for (const frame of frames) {
          if (!frame.trim()) continue;
          const parsed = parseSseFrame(frame);
          const typed = parseTypedEvent(parsed.data);

          if (typed?.type === 'step') {
            setThinkingSteps((current) => [
              ...current,
              {
                ...typed,
                elapsed: `${((performance.now() - streamStartedAt) / 1000).toFixed(1)}s`,
              },
            ]);
            if (typed.status === 'done' && typed.id === 'done') {
              setThinkingDone(true);
              setThinkingCollapsed(true);
            }
            continue;
          }

          if (typed?.type === 'content') {
            assistantText += typed.text || '';
            setCurrentResponse((prev) => prev + (typed.text || ''));
            continue;
          }

          if (typed?.type === 'sources') {
            streamedSources = Array.isArray(typed.sources) ? typed.sources : [];
            setCurrentSearchUsed(Boolean(typed.searchUsed));
            setCurrentSources(streamedSources);
            continue;
          }

          if (typed?.type === 'meta') {
            meta = typed;
            if (meta.memory) setMemory({ ...emptyMemory, ...meta.memory });
            if (meta.sources) setCurrentSources(meta.sources);
            setCurrentSearchUsed(Boolean(meta.searchUsed));
            if (meta.sessionId) setActiveSessionId(meta.sessionId);
            if (meta.title) setActiveTitle(meta.title);
            continue;
          }

          if (typed?.type === 'error') {
            setError(typed.text || 'AI service error.');
            continue;
          }

          if (typed?.type === 'done') {
            setThinkingDone(true);
            setThinkingCollapsed(true);
            continue;
          }

          if (parsed.event === 'step') {
            const step = JSON.parse(parsed.data);
            setThinkingSteps((current) => [...current, {
              ...step,
              elapsed: `${((performance.now() - streamStartedAt) / 1000).toFixed(1)}s`,
            }]);
            if (step.status === 'done' && step.id === 'done') {
              setThinkingDone(true);
              setThinkingCollapsed(true);
            }
            continue;
          }

          if (parsed.event === 'sources') {
            streamedSources = JSON.parse(parsed.data || '[]');
            setCurrentSearchUsed(streamedSources.length > 0);
            setCurrentSources(streamedSources);
            continue;
          }

          if (parsed.event === 'meta') {
            meta = JSON.parse(parsed.data);
            if (meta.memory) setMemory({ ...emptyMemory, ...meta.memory });
            if (meta.sources) setCurrentSources(meta.sources);
            setCurrentSearchUsed(Boolean(meta.searchUsed));
            if (meta.sessionId) setActiveSessionId(meta.sessionId);
            if (meta.title) setActiveTitle(meta.title);
            continue;
          }

          if (parsed.data === '[DONE]') continue;
          if (parsed.data.startsWith('[ERROR]')) {
            setError(parsed.data.replace('[ERROR]', '').trim());
            continue;
          }

          assistantText += parsed.data;
          setCurrentResponse((prev) => prev + parsed.data);
        }
      }

      setMessages([
        ...nextMessages.map((item, index) => index === nextMessages.length - 1 ? { ...item, status: 'received' } : item),
        {
          role: 'assistant',
          content: assistantText || 'I could not generate a response.',
          memoryUsed: Boolean(meta?.memoryUsed),
          sources: meta?.sources || streamedSources,
          searchUsed: Boolean(meta?.searchUsed),
          createdAt: new Date().toISOString(),
        },
      ]);
      setCurrentResponse('');
      await loadSessions();
      await loadMemory();
    } catch (err) {
      setError(err.message || 'Chat request failed.');
      setMessages(messages);
    } finally {
      setIsStreaming(false);
    }
  };

  const onInputKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const sendSuggestion = (suggestion) => {
    setInput(suggestion);
    window.setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const handleMessagesScroll = () => {
    const element = messagesRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    const near = distanceFromBottom < 120;
    setIsNearBottom(near);
    if (near) setShowScrollButton(false);
  };

  const scrollToLatest = () => {
    setIsNearBottom(true);
    setShowScrollButton(false);
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') {
        setMemoryOpen(false);
        setProfileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <main className={`nexus-workspace ${memoryOpen ? '' : 'memory-collapsed'}`}>
      <aside className="nexus-sidebar glass-card">
        <button className="new-chat-button" type="button" onClick={startNewChat}>
          <span>+</span>
          New chat
        </button>
        <input className="form-control chat-search" onChange={(event) => setSearch(event.target.value)} placeholder="Search chats..." value={search} />
        <div className="session-groups">
          {['Today', 'Yesterday', 'Last 7 days', 'Older'].map((label) => (
            groupedSessions[label]?.length ? (
              <section className="session-group" key={label}>
                <h2>{label}</h2>
                {groupedSessions[label].map((session) => (
                  <button className={`session-row ${session.id === activeSessionId ? 'active' : ''}`} key={session.id} onClick={() => loadSession(session)} type="button">
                    <span className="session-icon">□</span>
                    <span className="session-title">{session.title}</span>
                    <time>{formatTime(session.updatedAt || session.createdAt)}</time>
                    <span className="session-options" aria-hidden="true">...</span>
                  </button>
                ))}
              </section>
            ) : null
          ))}
          {!sessions.length ? <div className="empty-sidebar">No conversations yet.</div> : null}
        </div>
        <div className="sidebar-user-wrapper">
          {profileMenuOpen ? (
            <div className="profile-menu glass-card-sm">
              <button onClick={() => { setProfileModalOpen(true); setProfileMenuOpen(false); }} type="button">👤 Profile settings</button>
              <button type="button">🔔 Notifications</button>
              <button type="button">⚙️ Preferences</button>
              <hr />
              <button onClick={logout} type="button">🚪 Sign out</button>
            </div>
          ) : null}
        <button className="sidebar-user" onClick={() => setProfileMenuOpen((open) => !open)} type="button">
          <div className="user-avatar">{initials(storedUser)}</div>
          <div>
            <strong>{storedUser.name || 'Nexus user'}</strong>
            <span>{storedUser.email || 'Free plan'}</span>
          </div>
        </button>
        </div>
      </aside>

      <section className="nexus-chat glass-card">
        <header className="chat-topbar">
          <div>
            <h1>{activeTitle}</h1>
            <p>{memory.memoryEnabled === false ? 'Memory disabled' : 'Long-term memory enabled'}</p>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={shareChat} title="Share chat" type="button">Share</button>
          </div>
        </header>

        <div className={`nexus-messages ${hasMessages || isStreaming ? '' : 'empty'}`} onScroll={handleMessagesScroll} ref={messagesRef}>
          {renderedMessages.map((message, index) => (
            <MessageBubble
              copied={copiedId === (message.id || message.createdAt)}
              key={`${message.role}-${index}-${message.createdAt || index}`}
              message={message}
              onCopy={copyMessage}
              onReact={reactToMessage}
              user={storedUser}
            />
          ))}

          <ThinkingPanel
            collapsed={thinkingCollapsed}
            done={thinkingDone}
            onToggle={() => setThinkingCollapsed((current) => !current)}
            steps={thinkingSteps}
          />

          {isStreaming ? (
            <MessageBubble
              copied={false}
              message={{
                role: 'assistant',
                content: currentResponse,
                sources: currentSources,
                searchUsed: currentSearchUsed,
                streaming: true,
                createdAt: new Date().toISOString(),
              }}
              onCopy={copyMessage}
              onReact={reactToMessage}
              user={storedUser}
            />
          ) : null}
          <div ref={bottomRef} />
        </div>

        {showScrollButton ? (
          <button className="scroll-latest-button" onClick={scrollToLatest} type="button">↓ scroll to latest</button>
        ) : null}

        {error ? <div className="chat-error">{error}</div> : null}

        <form className={`nexus-composer advanced ${hasMessages || isStreaming ? 'bottom' : 'centered'}`} onSubmit={sendMessage} ref={formRef}>
          {!hasMessages && !isStreaming ? (
            <div className="empty-chat-hero">
              <span className="nexus-avatar large">N</span>
              <h2>Ask Nexus anything.</h2>
              <div className="suggestion-chips">
                {[
                  'Explain a complex topic simply',
                  'Write or debug code for me',
                  'Analyse an image or file',
                  'Search the web for something',
                ].map((suggestion) => (
                  <button key={suggestion} onClick={() => sendSuggestion(suggestion)} type="button">{suggestion}</button>
                ))}
              </div>
            </div>
          ) : null}

          {files.length ? (
            <div className="upload-preview-row">
              {files.map((preview, index) => (
                <div className="upload-preview" key={`${preview.name}-${index}`}>
                  {preview.url ? <img alt={preview.name} src={preview.url} /> : <span>📄</span>}
                  <div>
                    <strong>{preview.name}</strong>
                    <small>{fileSize(preview.size)}</small>
                  </div>
                  <button onClick={() => removeFile(index)} type="button">×</button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="composer-main">
            <button className="attach-button" onClick={() => fileInputRef.current?.click()} title="Attach images" type="button">+</button>
            <textarea
              className="form-control message-textarea"
              disabled={isStreaming}
              maxLength={2000}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={onInputKeyDown}
              placeholder="Message Nexus..."
              ref={textareaRef}
              rows={1}
              value={input}
            />
            <button className="send-button" disabled={isStreaming || (!input.trim() && !files.length)} type="submit">
              {isStreaming ? <TypingDots /> : 'Send'}
            </button>
          </div>

          <div className="input-toolbar">
            <button className="tool-chip" onClick={() => fileInputRef.current?.click()} type="button">+ Attach</button>
            <button className={`tool-chip ${deepThink ? 'active' : ''}`} onClick={() => setDeepThink((current) => !current)} type="button">{deepThink ? 'Thinking ✓' : 'Think'}</button>
            <button className={`tool-chip ${webSearch ? 'active' : ''}`} onClick={() => setWebSearch((current) => !current)} type="button">🌐 Web search</button>
            <button className={`tool-chip ${codeMode ? 'active' : ''}`} onClick={() => setCodeMode((current) => !current)} type="button">💻 Code</button>
            <button className={`tool-chip ${memoryOpen ? 'active' : ''}`} onClick={() => setMemoryOpen((current) => !current)} type="button">🧠 Memory</button>
            {input.length > 500 ? <span className="char-counter">{input.length} / 2000</span> : null}
          </div>

          <p className="input-disclaimer">Nexus can make mistakes. Always double-check important responses.</p>

          <input
            accept="image/jpeg,image/png,image/webp,image/gif"
            hidden
            multiple
            onChange={onFilesSelected}
            ref={fileInputRef}
            type="file"
          />
        </form>
      </section>

      {memoryOpen ? <button className="drawer-backdrop" aria-label="Close memory drawer" onClick={() => setMemoryOpen(false)} type="button" /> : null}
      {memoryOpen ? (
        <aside className="memory-panel glass-card">
          <header>
            <div>
              <span className="memory-mark">N</span>
              <h2>Long-term memory ({memoryCount} facts)</h2>
            </div>
            <button className="icon-button compact" onClick={() => setMemoryOpen(false)} type="button">...</button>
          </header>
          <div className="memory-list">
            {memory.name ? <MemoryItem label="NAME" value={memory.name} /> : null}
            {memory.location ? <MemoryItem label="LOCATION" value={memory.location} /> : null}
            {memory.occupation ? <MemoryItem label="OCCUPATION" value={memory.occupation} /> : null}
            {memory.interests?.length ? <MemoryItem label="INTERESTS" value={memory.interests.join(', ')} /> : null}
            {memory.facts?.length ? memory.facts.map((fact, index) => (
              <MemoryItem canDelete key={`${fact}-${index}`} label="FACTS" onDelete={() => deleteFact(index)} value={fact} />
            )) : null}
            {!memoryCount ? <div className="memory-empty">Nexus has not saved long-term facts yet.</div> : null}
          </div>
          <button className="clear-memory-button" onClick={clearMemory} type="button">Clear memory</button>
        </aside>
      ) : null}
      {profileModalOpen ? (
        <div className="modal-backdrop-custom">
          <form className="profile-modal glass-card" onSubmit={saveProfile}>
            <h2>Profile settings</h2>
            <label htmlFor="profile-name">Display name</label>
            <input id="profile-name" className="form-control" value={profileForm.name} onChange={(event) => setProfileForm((state) => ({ ...state, name: event.target.value }))} />
            {['currentPassword', 'password', 'confirmPassword'].map((field) => (
              <div key={field}>
                <label htmlFor={`profile-${field}`}>{field === 'currentPassword' ? 'Current password' : field === 'password' ? 'New password' : 'Confirm password'}</label>
                <div className="password-field">
                  <input
                    id={`profile-${field}`}
                    className="form-control"
                    type={showProfilePasswords[field] ? 'text' : 'password'}
                    value={profileForm[field]}
                    onChange={(event) => setProfileForm((state) => ({ ...state, [field]: event.target.value }))}
                  />
                  <button onClick={() => setShowProfilePasswords((state) => ({ ...state, [field]: !state[field] }))} type="button">
                    {showProfilePasswords[field] ? '◉' : '◌'}
                  </button>
                </div>
              </div>
            ))}
            <div className="profile-modal-actions">
              <button className="btn btn-nexus-ghost" onClick={() => setProfileModalOpen(false)} type="button">Cancel</button>
              <button className="btn btn-nexus-primary" type="submit">Save</button>
            </div>
          </form>
        </div>
      ) : null}
    </main>
  );
}

function MemoryItem({ canDelete = false, label, onDelete, value }) {
  return (
    <div className="memory-item fade-in">
      <span>{label}</span>
      <strong>{value}</strong>
      {canDelete ? <button onClick={onDelete} title="Delete fact" type="button">×</button> : null}
    </div>
  );
}
