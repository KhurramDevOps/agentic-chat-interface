import React, { useEffect, useRef, useState } from 'react';
import AgentToolsBar from './AgentToolsBar';
import FileUploadPreview from './FileUploadPreview';
import LoadingSpinner from '../ui/LoadingSpinner';
import { useFileUpload } from '../../hooks/useFileUpload';

export default function MessageInput({ disabled, onSend }) {
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const uploadFile = useFileUpload();
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [tools, setTools] = useState({ search: false, image: false, analysis: false });

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
  }, [text]);

  const toggleTool = (key) => setTools((current) => ({ ...current, [key]: !current[key] }));

  const handleFile = async (event) => {
    const selected = event.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setUploadedFile(null);
    const result = await uploadFile.mutateAsync(selected);
    setUploadedFile(result);
  };

  const removeFile = () => {
    setFile(null);
    setUploadedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const buildMessage = () => {
    const prefixes = [];
    if (tools.search) prefixes.push('[SEARCH]');
    if (tools.image) prefixes.push('[IMAGE]');
    if (tools.analysis) prefixes.push('[ANALYSIS]');
    const fileLine = uploadedFile ? `[File: ${uploadedFile.filename || file?.name}](${uploadedFile.url})` : '';
    return [prefixes.join(' '), fileLine, text.trim()].filter(Boolean).join('\n');
  };

  const submit = async () => {
    const message = buildMessage();
    if (!message || disabled || uploadFile.isPending) return;
    await onSend(message);
    setText('');
    removeFile();
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="message-input-shell glass-card">
      <AgentToolsBar tools={tools} onToggle={toggleTool} />
      <div className="d-flex align-items-end gap-2">
        <input
          accept="image/*,application/pdf,.txt,.md,.csv,.json,.py,.js"
          className="d-none"
          onChange={handleFile}
          ref={fileInputRef}
          type="file"
        />
        <button className="btn btn-nexus-ghost" onClick={() => fileInputRef.current?.click()} title="Attach file" type="button">
          <i className="bi bi-paperclip" />
        </button>
        <textarea
          className="form-control message-textarea"
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message Nexus..."
          ref={textareaRef}
          rows={1}
          value={text}
        />
        <button className="btn btn-nexus-primary" disabled={disabled || uploadFile.isPending || !buildMessage()} onClick={submit} type="button">
          {disabled ? <LoadingSpinner size="sm" /> : <i className="bi bi-send-fill" />}
        </button>
      </div>
      <FileUploadPreview file={file} uploadedFile={uploadedFile} isUploading={uploadFile.isPending} onRemove={removeFile} />
    </div>
  );
}
