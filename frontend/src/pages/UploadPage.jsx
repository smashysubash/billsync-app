import { useState, useRef, useEffect } from 'react';
import { uploadInvoice, processInvoice } from '../api';
import { Icon } from '../icons.jsx';

// ——— Processing screen (animated step list) ———
function ProcessingScreen({ onDone, onError }) {
  const [stage, setStage] = useState(0);
  const stages = [
    'Reading PDF',
    'Extracting line items',
    'Matching to your products',
    'Checking price history',
  ];

  // The actual work is done by the caller; this just animates while we wait.
  // onDone() is called externally when the API returns.
  useEffect(() => {
    const timers = [
      setTimeout(() => setStage(1), 600),
      setTimeout(() => setStage(2), 1400),
      setTimeout(() => setStage(3), 2400),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="upload-wrap">
      <div className="upload-card">
        <h1 className="upload-title">Processing invoice</h1>
        <p className="upload-sub">This usually takes a few seconds.</p>

        <div className="progress-bar">
          <div style={{ width: `${Math.min(100, (stage + 1) * 25)}%` }}/>
        </div>

        <div className="proc-steps">
          {stages.map((label, i) => (
            <div
              key={i}
              className={`proc-step ${i === stage ? 'active' : i < stage ? 'done' : ''}`}
            >
              <div className="proc-dot">
                {i < stage && <Icon.check size={10}/>}
              </div>
              {label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ——— Upload screen ———
export default function UploadPage({ onProcessed }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const pickFile = (f) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setError('Please select a PDF file.');
      return;
    }
    setError(null);
    setFile(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files[0]);
  };

  const useSample = () => {
    // Fake file object so the UI shows the sample file name
    setFile({ name: 'PI-870 Milky Mist — 13 Feb 2026.pdf', size: 184320, _sample: true });
    setError(null);
  };

  async function handleProcess() {
    if (!file) return;
    setError(null);
    setProcessing(true);
    try {
      const uploaded = await uploadInvoice(file);
      const processed = await processInvoice(uploaded.text, uploaded.file_path);
      onProcessed(processed);
    } catch (e) {
      setProcessing(false);
      setError(e.message);
    }
  }

  if (processing) {
    return <ProcessingScreen/>;
  }

  return (
    <div className="upload-wrap">
      <div className="upload-card">
        <h1 className="upload-title">Upload vendor invoice</h1>
        <p className="upload-sub">
          Drag a PDF here, or click to browse. We'll read it and prepare a bill for review.
        </p>

        {error && (
          <div className="error-banner" style={{ marginBottom: 16 }}>
            <Icon.warn size={16}/>
            <span>{error}</span>
          </div>
        )}

        {!file ? (
          <div
            className={`dropzone ${dragging ? 'dragging' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <div className="dz-icon"><Icon.upload size={26}/></div>
            <div className="dz-title">Drop invoice PDF here</div>
            <div className="dz-hint">or click to choose from your computer · up to 10 MB</div>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              style={{ display: 'none' }}
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
          </div>
        ) : (
          <div className="dropzone has-file">
            <div className="dz-icon"><Icon.pdf size={22}/></div>
            <div className="dz-file-meta">
              <div className="dz-file-name">{file.name}</div>
              <div className="dz-file-size">
                {file.size ? `${(file.size / 1024).toFixed(0)} KB · ` : ''}ready to process
              </div>
            </div>
            <button
              className="dz-remove"
              onClick={() => setFile(null)}
              title="Remove file"
            >
              <Icon.x size={18}/>
            </button>
          </div>
        )}

        <div className="upload-actions">
          {/* <button className="btn btn-ghost" onClick={useSample}>
            Use sample invoice
          </button> */}
          <button
            className="btn btn-primary btn-lg"
            disabled={!file}
            onClick={handleProcess}
          >
            Process invoice
          </button>
        </div>
      </div>
    </div>
  );
}
