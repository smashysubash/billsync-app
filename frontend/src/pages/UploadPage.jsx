import { useState, useRef } from 'react';
import { uploadInvoice, processInvoice } from '../api';

export default function UploadPage({ onProcessed }) {
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  async function handleFile(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please select a PDF file.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const uploaded = await uploadInvoice(file);
      const processed = await processInvoice(uploaded.text, uploaded.file_path);
      onProcessed(processed);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    handleFile(file);
  }

  function onInputChange(e) {
    handleFile(e.target.files[0]);
  }

  if (loading) {
    return (
      <div className="upload-page">
        <div className="spinner-wrap">
          <div className="spinner" />
          <p className="spinner-label">Extracting invoice data…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="upload-page">
      <div className="upload-hero">
        <h1>Turn invoices into bills</h1>
        <p>Upload a Milky Mist PDF invoice — we'll handle the rest.</p>
      </div>

      {error && <div className="error-banner" style={{ maxWidth: 560, width: '100%', marginBottom: 20 }}>⚠ {error}</div>}

      <div
        className={`drop-zone${dragOver ? ' drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <div className="drop-icon">📄</div>
        <h2>Drop your PDF here</h2>
        <p>or click to browse</p>
        <button className="btn btn-primary" onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}>
          Select PDF
        </button>
        <p className="upload-hint">Milky Mist invoices only · Max 25 MB</p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={onInputChange}
      />
    </div>
  );
}
