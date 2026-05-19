import React, { useEffect, useMemo, useState } from 'react';
import { formatFileSize } from '../../utils/timeUtils';

export default function FileUploadPreview({ file, uploadedFile, isUploading, onRemove }) {
  const [preview, setPreview] = useState('');

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) {
      setPreview('');
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const icon = useMemo(() => {
    if (!file) return 'bi-file-earmark';
    if (file.type.startsWith('image/')) return 'bi-file-earmark-image';
    if (file.type.includes('pdf')) return 'bi-filetype-pdf';
    if (file.name.endsWith('.js')) return 'bi-filetype-js';
    if (file.name.endsWith('.py')) return 'bi-filetype-py';
    return 'bi-file-earmark-text';
  }, [file]);

  if (!file) return null;

  return (
    <div className="glass-card-sm p-3 mt-2">
      <div className="d-flex align-items-center gap-3">
        {preview ? (
          <img className="file-preview-thumb" src={preview} alt={file.name} />
        ) : (
          <i className={`bi ${icon} fs-3 text-accent`} />
        )}
        <div className="flex-grow-1">
          <div className="d-flex justify-content-between gap-2">
            <strong className="text-truncate">{file.name}</strong>
            <button className="btn btn-sm btn-nexus-ghost" onClick={onRemove} type="button" aria-label="Remove file">
              <i className="bi bi-x" />
            </button>
          </div>
          <span className="text-secondary small">{formatFileSize(file.size)}</span>
        </div>
      </div>
      {isUploading ? (
        <div className="progress mt-3" style={{ height: 6 }}>
          <div className="progress-bar progress-bar-striped progress-bar-animated" style={{ width: '82%' }} />
        </div>
      ) : null}
      {uploadedFile ? <div className="text-success small mt-2"><i className="bi bi-check-circle me-1" />Uploaded</div> : null}
    </div>
  );
}
