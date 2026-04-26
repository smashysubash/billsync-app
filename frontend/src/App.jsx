import { useState, useCallback } from 'react';
import './index.css';
import UploadPage from './pages/UploadPage';
import ReviewPage from './pages/ReviewPage';

function Toast({ toasts }) {
  return (
    <div className="toast-wrap">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.type}`}>
          <div className="toast-title">{t.title}</div>
          {t.body && <div className="toast-body">{t.body}</div>}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState('upload'); // 'upload' | 'review'
  const [reviewData, setReviewData] = useState(null);
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((type, title, body) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, type, title, body }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
  }, []);

  function handleProcessed(data) {
    setReviewData(data);
    setPage('review');
  }

  function handleReset() {
    setReviewData(null);
    setPage('upload');
  }

  return (
    <div className="app-shell">
      {/* Top bar */}
      <header className="topbar">
        <a className="topbar-logo" href="/" onClick={(e) => { e.preventDefault(); handleReset(); }}>
          <div className="logo-mark">B</div>
          <span className="logo-name">BillSync</span>
        </a>
        <div className="topbar-spacer" />
        {page === 'review' && (
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            📄 {reviewData?.meta?.invoice_number ?? 'Invoice Review'}
          </span>
        )}
      </header>

      {/* Main */}
      <main className="main-content">
        {page === 'upload' && <UploadPage onProcessed={handleProcessed} />}
        {page === 'review' && reviewData && (
          <ReviewPage data={reviewData} onReset={handleReset} onToast={addToast} />
        )}
      </main>

      <Toast toasts={toasts} />
    </div>
  );
}
