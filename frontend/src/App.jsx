import { useState, useCallback, useEffect, useRef } from 'react';
import './index.css';
import { Icon, formatINR } from './icons.jsx';
import UploadPage from './pages/UploadPage';
import ReviewPage from './pages/ReviewPage';
import { zohoStatus, zohoConnect, zohoSaveConfig, syncZohoItems } from './api.js';

// ——— Topbar with breadcrumb steps ———
function TopBar({ step, zohoConnected, onSettings, onSync, syncing }) {
  const steps = [
    { label: 'Upload', key: 'upload' },
    { label: 'Review',  key: 'review' },
    { label: 'Confirm', key: 'done' },
  ];
  const currentIdx = steps.findIndex(s => s.key === step);

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">B</div>
        BillSync
      </div>

      <div className="steps">
        {steps.map((s, i) => (
          <span key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className={`step ${i === currentIdx ? 'current' : i < currentIdx ? 'done' : ''}`}>
              <div className="step-num">
                {i < currentIdx ? <Icon.check size={10}/> : i + 1}
              </div>
              {s.label}
            </div>
            {i < steps.length - 1 && (
              <span className="step-sep">›</span>
            )}
          </span>
        ))}
      </div>

      <div className="topbar-spacer"/>

      <div className="topbar-user">
        {/* Sync button */}
        {zohoConnected && (
          <button
            className={`sync-items-btn ${syncing ? 'is-syncing' : ''}`}
            onClick={onSync}
            disabled={syncing}
            title="Sync products from Zoho Books"
          >
            <Icon.sync size={14}/>
            {syncing ? 'Syncing...' : 'Sync Items'}
          </button>
        )}

        {/* Zoho connection indicator */}
        <button
          className="zoho-status-btn"
          onClick={onSettings}
          title={zohoConnected ? 'Zoho Books connected' : 'Connect Zoho Books'}
        >
          <span className={`zoho-dot ${zohoConnected ? 'ok' : 'off'}`}/>
          Zoho Books
        </button>
        <div className="avatar" title="Settings" onClick={onSettings} style={{ cursor: 'pointer' }}>⚙</div>
      </div>
    </header>
  );
}


// ——— Zoho Settings Panel ———
function ZohoSettingsPanel({ onClose, onToast }) {
  const [status, setStatus] = useState(null);
  const [tab, setTab]       = useState('oauth');   // 'oauth' | 'manual'
  const [clientId, setClientId]         = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [refreshToken, setRefreshToken] = useState('');
  const [orgId, setOrgId]               = useState('');
  const [busy, setBusy] = useState(false);
  const popupRef = useRef(null);
  const pollRef  = useRef(null);

  useEffect(() => {
    zohoStatus().then(setStatus).catch(() => {});
    return () => { clearInterval(pollRef.current); };
  }, []);

  async function handleOAuthConnect() {
    if (!clientId.trim() || !clientSecret.trim()) {
      onToast('error', 'Missing fields', 'Enter Client ID and Client Secret.');
      return;
    }
    setBusy(true);
    try {
      const { auth_url } = await zohoConnect(clientId.trim(), clientSecret.trim());
      // Open consent screen in a popup
      popupRef.current = window.open(auth_url, 'zoho_oauth',
        'width=600,height=700,left=300,top=100');
      // Poll every second until the popup closes, then refresh status
      pollRef.current = setInterval(() => {
        if (popupRef.current?.closed) {
          clearInterval(pollRef.current);
          zohoStatus().then(s => {
            setStatus(s);
            if (s.connected) {
              onToast('success', 'Zoho Books connected!',
                `Organization ${s.organization_id} ready.`);
            }
          });
          setBusy(false);
        }
      }, 1000);
    } catch (e) {
      onToast('error', 'Connect failed', e.message);
      setBusy(false);
    }
  }

  async function handleManualSave() {
    if (!clientId || !clientSecret || !refreshToken) {
      onToast('error', 'Missing fields', 'Client ID, Secret and Refresh Token are required.');
      return;
    }
    setBusy(true);
    try {
      await zohoSaveConfig(clientId, clientSecret, refreshToken, orgId);
      const s = await zohoStatus();
      setStatus(s);
      onToast('success', 'Credentials saved', 'Zoho Books is now connected.');
    } catch (e) {
      onToast('error', 'Save failed', e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="settings-panel">
        <div className="settings-head">
          <div className="settings-title">⚙ Zoho Books Connection</div>
          <button className="settings-close" onClick={onClose}>✕</button>
        </div>

        {/* Status badge */}
        <div className="settings-status">
          <span className={`zoho-dot ${status?.connected ? 'ok' : 'off'}`}/>
          {status?.connected
            ? <>Connected · Org <strong>{status.organization_id}</strong></>
            : 'Not connected'}
        </div>

        {/* Tab switcher */}
        <div className="settings-tabs">
          <button className={`stab ${tab === 'oauth' ? 'active' : ''}`}
            onClick={() => setTab('oauth')}>OAuth (recommended)</button>
          <button className={`stab ${tab === 'manual' ? 'active' : ''}`}
            onClick={() => setTab('manual')}>Manual / Refresh Token</button>
        </div>

        {tab === 'oauth' && (
          <div className="settings-body">
            <p className="settings-hint">
              1. Go to <a href="https://api-console.zoho.com" target="_blank" rel="noreferrer">api-console.zoho.com</a>
              → Add Client → <strong>Self Client</strong> → Create.<br/>
              2. Copy <strong>Client ID</strong> and <strong>Client Secret</strong> below, then click Connect.<br/>
              3. Approve in the popup — tokens are saved automatically.
            </p>
            <label className="s-label">Client ID</label>
            <input className="s-input" value={clientId}
              onChange={e => setClientId(e.target.value)} placeholder="1000.XXXXXXXX…"/>
            <label className="s-label">Client Secret</label>
            <input className="s-input" type="password" value={clientSecret}
              onChange={e => setClientSecret(e.target.value)} placeholder="••••••••"/>
            <button className="btn btn-primary" style={{ marginTop: 16 }}
              disabled={busy} onClick={handleOAuthConnect}>
              {busy ? 'Waiting for approval…' : '🔗 Connect to Zoho Books'}
            </button>
          </div>
        )}

        {tab === 'manual' && (
          <div className="settings-body">
            <p className="settings-hint">
              Paste credentials directly if you already have a refresh token.
            </p>
            <label className="s-label">Client ID</label>
            <input className="s-input" value={clientId}
              onChange={e => setClientId(e.target.value)} placeholder="1000.XXXXXXXX…"/>
            <label className="s-label">Client Secret</label>
            <input className="s-input" type="password" value={clientSecret}
              onChange={e => setClientSecret(e.target.value)} placeholder="••••••••"/>
            <label className="s-label">Refresh Token</label>
            <input className="s-input" value={refreshToken}
              onChange={e => setRefreshToken(e.target.value)} placeholder="1000.XXXX…"/>
            <label className="s-label">Organization ID <span style={{opacity:.5}}>(optional — auto-detected)</span></label>
            <input className="s-input" value={orgId}
              onChange={e => setOrgId(e.target.value)} placeholder="123456789"/>
            <button className="btn btn-primary" style={{ marginTop: 16 }}
              disabled={busy} onClick={handleManualSave}>
              {busy ? 'Saving…' : '💾 Save credentials'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ——— Toast ———
function Toast({ toasts }) {
  return (
    <>
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.type}`}>
          <div className="ok-circle">
            {t.type === 'error'
              ? <Icon.warn size={12}/>
              : <Icon.check size={12}/>}
          </div>
          <div>
            <div>{t.title}</div>
            {t.body && <div className="toast-body">{t.body}</div>}
          </div>
        </div>
      ))}
    </>
  );
}

// ——— Main App ———
export default function App() {
  const [reviewData, setReviewData] = useState(() => {
    try {
      const saved = sessionStorage.getItem('bs-review-data');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });
  const [successData, setSuccessData] = useState(() => {
    try {
      const saved = sessionStorage.getItem('bs-success-data');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  // Derive screen from persisted value, but fall back to 'upload'
  // if the required data isn't available (stale sessionStorage).
  const [screen, setScreen] = useState(() => {
    const saved = sessionStorage.getItem('bs-screen') || 'upload';
    try {
      if (saved === 'review') {
        const data = sessionStorage.getItem('bs-review-data');
        return data ? 'review' : 'upload';
      }
      if (saved === 'done') {
        const data = sessionStorage.getItem('bs-success-data');
        return data ? 'done' : 'upload';
      }
    } catch { /* ignore */ }
    return saved;
  });
  const [toasts, setToasts]           = useState([]);
  const [showSettings, setShowSettings] = useState(false);
  const [zohoConnected, setZohoConnected] = useState(false);
  const [syncing, setSyncing]             = useState(false);

  // Check Zoho connection on mount
  useEffect(() => {
    zohoStatus().then(s => setZohoConnected(!!s.connected)).catch(() => {});
  }, []);

  async function handleSync() {
    setSyncing(true);
    try {
      const res = await syncZohoItems();
      addToast('success', 'Sync complete', `${res.synced_items} items cached from Zoho Books.`);
    } catch (e) {
      addToast('error', 'Sync failed', e.message);
    } finally {
      setSyncing(false);
    }
  }

  // Keep sessionStorage in sync with state
  useEffect(() => {
    sessionStorage.setItem('bs-screen', screen);
  }, [screen]);

  useEffect(() => {
    if (reviewData) {
      sessionStorage.setItem('bs-review-data', JSON.stringify(reviewData));
    } else {
      sessionStorage.removeItem('bs-review-data');
    }
  }, [reviewData]);

  useEffect(() => {
    if (successData) {
      sessionStorage.setItem('bs-success-data', JSON.stringify(successData));
    } else {
      sessionStorage.removeItem('bs-success-data');
    }
  }, [successData]);

  const addToast = useCallback((type, title, body) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, type, title, body }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
  }, []);

  function handleProcessed(data) {
    setReviewData(data);
    setScreen('review');
  }

  function handleConfirmed(result) {
    setSuccessData(result);
    setScreen('done');
  }

  function handleReset() {
    setReviewData(null);
    setSuccessData(null);
    setScreen('upload');
  }

  const step =
    screen === 'done' ? 'done' :
    screen === 'review' || screen === 'processing' ? 'review' : 'upload';

  return (
    <div className="app">
      <TopBar
        step={step}
        zohoConnected={zohoConnected}
        onSettings={() => setShowSettings(true)}
        onSync={handleSync}
        syncing={syncing}
      />

      {showSettings && (
        <ZohoSettingsPanel
          onClose={() => {
            setShowSettings(false);
            // Refresh connection status after closing settings
            zohoStatus().then(s => setZohoConnected(!!s.connected)).catch(() => {});
          }}
          onToast={addToast}
        />
      )}

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {(screen === 'upload' || screen === 'processing') && (
          <UploadPage onProcessed={handleProcessed}/>
        )}
        {screen === 'review' && reviewData && (
          <ReviewPage
            data={reviewData}
            onReset={handleReset}
            onConfirmed={handleConfirmed}
            onToast={addToast}
          />
        )}
        {screen === 'done' && (
          <SuccessScreen data={successData} onNew={handleReset}/>
        )}
      </main>

      <Toast toasts={toasts}/>
    </div>
  );
}

// ——— Success screen ———
function SuccessScreen({ data, onNew }) {
  return (
    <div className="success-wrap">
      <div className="success-card">
        <div className="success-check">
          <Icon.checkBig size={36}/>
        </div>
        <h1 className="success-title">Purchase bill created</h1>
        <p className="success-sub">Sent to Zoho Books under Sree Agency.</p>

        <div className="success-detail">
          {data?.zoho_bill_id && (
            <div className="success-row">
              <div className="l">Bill number</div>
              <div className="v link">{data.zoho_bill_id} ↗</div>
            </div>
          )}
          <div className="success-row">
            <div className="l">Vendor</div>
            <div className="v">{data?.vendor ?? 'Milky Mist Dairy Food Ltd.'}</div>
          </div>
          <div className="success-row">
            <div className="l">Total</div>
            <div className="v num">{formatINR(data?.grand_total)}</div>
          </div>
          <div className="success-row">
            <div className="l">Items</div>
            <div className="v">{data?.item_count ?? '—'} lines</div>
          </div>
          {!data?.zoho_bill_id && (
            <div className="success-row" style={{ marginTop: 4 }}>
              <div className="l" style={{ color: 'var(--warn)', fontSize: 13 }}>
                Note: Invoice saved locally — configure VENDOR_ZOHO_ID to push bills to Zoho.
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
          {data?.zoho_bill_id && (
            <button className="btn btn-secondary">
              View in Zoho Books ↗
            </button>
          )}
          <button className="btn btn-primary" onClick={onNew}>
            Process another invoice
          </button>
        </div>
      </div>
    </div>
  );
}
