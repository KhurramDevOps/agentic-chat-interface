import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ImageMessage from './ImageMessage';
import { formatRelativeTime } from '../../utils/timeUtils';

const IMAGE_URL_REGEX = /(https?:\/\/[^\s)]+?\.(?:png|jpe?g|webp|gif)(?:\?[^\s)]*)?)/i;

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  const text = String(children || '').replace(/\n$/, '');

  const copyCode = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="position-relative">
      <button className="btn btn-sm btn-nexus-ghost position-absolute top-0 end-0 m-2" onClick={copyCode} type="button">
        {copied ? 'Copied' : 'Copy'}
      </button>
      <pre><code>{text}</code></pre>
    </div>
  );
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const content = String(message.content || '');

  const imageSource = useMemo(() => {
    if (content.startsWith('![')) {
      const match = content.match(/\((.*?)\)/);
      return match?.[1] || '';
    }
    return content.match(IMAGE_URL_REGEX)?.[1] || '';
  }, [content]);

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser ? <span className="nexus-avatar">N</span> : null}
      <div>
        <div className={`message-bubble ${isUser ? 'user' : 'assistant glass-card-sm'}`}>
          {imageSource ? (
            <ImageMessage src={imageSource} />
          ) : isUser ? (
            <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>
          ) : (
            <div className="markdown-content">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  pre: ({ children }) => children,
                  code: ({ inline, children }) => inline ? <code>{children}</code> : <CodeBlock>{children}</CodeBlock>,
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          )}
        </div>
        <div className={`message-time mt-1 ${isUser ? 'text-end' : ''}`}>
          {formatRelativeTime(message.createdAt || message.created_at)}
        </div>
      </div>
    </div>
  );
}
