import { useState, useCallback } from 'react';
import { confirmInvoice, saveMapping, syncZohoItems } from '../api';

const STATUS_LABEL = {
  normal: '✅ Normal',
  price_change: '⚠ Price Changed',
  new_product: '🔴 New Product',
};

const STATUS_CLASS = {
  normal: 'badge-normal',
  price_change: 'badge-price_change',
  new_product: 'badge-new_product',
};

function fmt(n) {
  return typeof n === 'number' ? n.toFixed(2) : '—';
}

export default function ReviewPage({ data, onReset, onToast }) {
  const { meta, items: initialItems } = data;

  const [items, setItems] = useState(
    initialItems.map((item, i) => ({ ...item, _id: i, removed: false }))
  );
  const [confirming, setConfirming] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Update mapping selection for an item
  const setItemMapping = useCallback((id, zohoItemId, zohoItemName) => {
    setItems(prev =>
      prev.map(item =>
        item._id === id
          ? { ...item, zoho_item_id: zohoItemId, zoho_item_name: zohoItemName,
              status: zohoItemId ? 'normal' : 'new_product', mapped: !!zohoItemId }
          : item
      )
    );
    // Persist mapping immediately
    const item = items.find(i => i._id === id);
    if (item && zohoItemId) {
      saveMapping(item.product_name, zohoItemId, zohoItemName).catch(() => {});
    }
  }, [items]);

  const removeItem = (id) =>
    setItems(prev => prev.map(i => i._id === id ? { ...i, removed: true } : i));

  const activeItems = items.filter(i => !i.removed);
  const unmapped = activeItems.filter(i => !i.mapped).length;
  const priceChanged = activeItems.filter(i => i.status === 'price_change').length;
  const totalAmount = activeItems.reduce((s, i) => s + (i.amount ?? 0), 0);

  async function handleSync() {
    setSyncing(true);
    try {
      const res = await syncZohoItems();
      onToast('success', 'Sync complete', `${res.synced_items} items cached from Zoho.`);
    } catch (e) {
      onToast('error', 'Sync failed', e.message);
    } finally {
      setSyncing(false);
    }
  }

  async function handleConfirm() {
    if (unmapped > 0) {
      onToast('error', 'Unmapped products', `Please map all ${unmapped} unmatched product(s) before confirming.`);
      return;
    }
    setConfirming(true);
    try {
      const res = await confirmInvoice({
        invoice_number: meta.invoice_number ?? 'UNKNOWN',
        invoice_date: meta.invoice_date ?? new Date().toISOString().slice(0, 10),
        vendor_zoho_id: null, // can be set via env/config in future
        line_items: activeItems.map(i => ({
          index: i.index,
          product_name: i.product_name,
          zoho_item_id: i.zoho_item_id,
          zoho_item_name: i.zoho_item_name,
          qty: i.qty,
          rate: i.rate,
          amount: i.amount,
        })),
      });
      if (res.zoho_bill_id) {
        onToast('success', 'Bill created!', `Zoho Bill ID: ${res.zoho_bill_id}`);
      } else if (res.zoho_error) {
        onToast('error', 'Invoice saved (Zoho error)', res.zoho_error);
      } else {
        onToast('success', 'Invoice confirmed', 'Saved locally — configure Zoho credentials to create bills.');
      }
      setTimeout(onReset, 3500);
    } catch (e) {
      onToast('error', 'Confirmation failed', e.message);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="review-header">
        <div>
          <h1>Review Invoice</h1>
          <div className="invoice-meta">
            {meta.invoice_number && (
              <span className="meta-chip">📋 Invoice <strong>{meta.invoice_number}</strong></span>
            )}
            {meta.invoice_date && (
              <span className="meta-chip">📅 <strong>{meta.invoice_date}</strong></span>
            )}
            <span className="meta-chip">🏢 <strong>{meta.vendor}</strong></span>
          </div>
        </div>
        <div className="review-actions">
          <button className="btn btn-ghost btn-sm" onClick={handleSync} disabled={syncing}>
            {syncing ? '⟳ Syncing…' : '⟳ Sync Zoho Items'}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={onReset}>← New Invoice</button>
        </div>
      </div>

      {/* Summary strip */}
      <div className="summary-strip">
        <div className="strip-card">
          <div className="label">Total Items</div>
          <div className="value">{activeItems.length}</div>
        </div>
        <div className={`strip-card ${unmapped > 0 ? 'danger' : 'success'}`}>
          <div className="label">Unmapped</div>
          <div className="value">{unmapped}</div>
        </div>
        <div className={`strip-card ${priceChanged > 0 ? 'warning' : ''}`}>
          <div className="label">Price Changes</div>
          <div className="value">{priceChanged}</div>
        </div>
        <div className="strip-card">
          <div className="label">Total Amount</div>
          <div className="value">₹{fmt(totalAmount)}</div>
        </div>
      </div>

      {/* Table */}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Vendor Product Name</th>
              <th>Zoho Item Mapping</th>
              <th className="num-cell">Qty</th>
              <th className="num-cell">Rate</th>
              <th className="num-cell">Amount</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item._id} className={item.removed ? 'removed' : ''}>
                <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{item.index}</td>

                {/* Vendor name */}
                <td className="product-cell">
                  <div className="product-name-display">{item.product_name}</div>
                </td>

                {/* Zoho mapping */}
                <td style={{ minWidth: 240 }}>
                  {item.candidates && item.candidates.length > 0 ? (
                    <div>
                      {item.mapped && (
                         <div className="product-zoho-name" style={{ marginBottom: 4, color: 'var(--success)' }}>
                            ✓ Current: {item.zoho_item_name}
                         </div>
                      )}
                      <select
                        className="mapping-select"
                        value={item.zoho_item_id || ""}
                        onChange={e => {
                          const selected = item.candidates.find(c => c.zoho_item_id === e.target.value);
                          if (selected) setItemMapping(item._id, selected.zoho_item_id, selected.zoho_item_name);
                        }}
                      >
                        <option value="" disabled>{item.mapped ? "Change mapping..." : "— Select match —"}</option>
                        {item.candidates.map(c => (
                          <option key={c.zoho_item_id} value={c.zoho_item_id}>
                            {c.zoho_item_name} ({c.score}%)
                          </option>
                        ))}
                      </select>
                      {item.status === 'price_change' && item.price_detail?.previous_rate && (
                        <div className="price-change-hint">
                          Prev rate: ₹{fmt(item.price_detail.previous_rate)}
                        </div>
                      )}
                    </div>
                  ) : (
                    <span style={{ color: 'var(--danger)', fontSize: 13 }}>
                      No matches — sync Zoho items
                    </span>
                  )}
                </td>

                <td className="num-cell">{item.qty}</td>
                <td className="num-cell">₹{fmt(item.rate)}</td>
                <td className="num-cell" style={{ fontWeight: 600 }}>₹{fmt(item.amount)}</td>

                {/* Status badge */}
                <td>
                  <span className={`badge ${STATUS_CLASS[item.status] ?? 'badge-normal'}`}>
                    {STATUS_LABEL[item.status] ?? item.status}
                  </span>
                </td>

                {/* Remove */}
                <td>
                  {!item.removed ? (
                    <button className="btn btn-danger btn-sm" onClick={() => removeItem(item._id)}>
                      ✕
                    </button>
                  ) : (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setItems(prev => prev.map(i => i._id === item._id ? { ...i, removed: false } : i))}
                    >
                      ↩
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Confirm footer */}
      <div className="confirm-footer">
        <div className="confirm-totals">
          <div className="total-item">
            <div className="label">Active Items</div>
            <div className="amount">{activeItems.length}</div>
          </div>
          <div className="total-item">
            <div className="label">Total</div>
            <div className="amount">₹{fmt(totalAmount)}</div>
          </div>
        </div>
        <button
          className="btn btn-primary btn-lg"
          onClick={handleConfirm}
          disabled={confirming || unmapped > 0}
          style={unmapped > 0 ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
        >
          {confirming ? '⟳ Creating Bill…' : '✓ Confirm & Create Bill'}
        </button>
      </div>
    </div>
  );
}
