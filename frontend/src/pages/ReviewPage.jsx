import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { confirmInvoice, saveMapping, syncZohoItems } from '../api';
import { Icon, formatINR } from '../icons.jsx';

// ——— Status badge ———
function Badge({ status }) {
  if (status === 'ok')
    return <span className="badge badge-ok"><span className="dot"/>OK</span>;
  if (status === 'price-changed')
    return <span className="badge badge-warn"><span className="dot"/>Price changed</span>;
  if (status === 'new-product')
    return <span className="badge badge-err"><span className="dot"/>New product</span>;
  if (status === 'unmapped')
    return <span className="badge badge-err"><span className="dot"/>Needs mapping</span>;
  return null;
}

// ——— Product picker floating dropdown ———
function ProductPicker({ row, products, onSelect, onClose, onCreateNew }) {
  const [q, setQ] = useState('');
  const inputRef = useRef(null);
  const pickerRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onClick = (e) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) onClose();
    };
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    setTimeout(() => document.addEventListener('mousedown', onClick), 0);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return products;
    return products.filter(p =>
      p.name.toLowerCase().includes(query) ||
      (p.sku && p.sku.toLowerCase().includes(query))
    );
  }, [q, products]);

  return (
    <div className="picker" ref={pickerRef}>
      <input
        ref={inputRef}
        className="picker-search"
        placeholder="Search by product name…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="picker-list">
        {filtered.length === 0 ? (
          <div className="picker-empty">
            No match found
            <div style={{ marginTop: 10 }}>
              <button
                className="btn btn-secondary"
                style={{ height: 34, fontSize: 13 }}
                onClick={() => { onCreateNew(q || row.extractedName); onClose(); }}
              >
                <Icon.plus size={14}/>
                Create "{q || row.extractedName}"
              </button>
            </div>
          </div>
        ) : filtered.map(p => (
          <button
            key={p.id}
            className={`picker-item ${row.mappedId === p.id ? 'active' : ''}`}
            onClick={() => { onSelect(p); onClose(); }}
          >
            <div style={{ fontWeight: 500 }}>{p.name}</div>
            <div className="sku">
              {p.sku ? `${p.sku} · ` : ''}
              {p.score != null ? `${p.score}% match` : ''}
              {p.lastRate != null ? ` · last rate ${formatINR(p.lastRate)}` : ''}
            </div>
          </button>
        ))}
      </div>
      <div className="picker-foot">
        <span><kbd>↑↓</kbd> navigate</span>
        <span><kbd>Enter</kbd> select</span>
        <span><kbd>Esc</kbd> close</span>
      </div>
    </div>
  );
}

// ——— Filter chip ———
function FilterChip({ active, onClick, children }) {
  return (
    <button className={`filter-chip ${active ? 'active' : ''}`} onClick={onClick}>
      {children}
    </button>
  );
}

// ——— PDF preview side panel ———
function PdfPreviewPanel({ meta, rows }) {
  return (
    <div className="pdf-panel">
      <div className="pdf-head">
        <Icon.pdf size={14}/>
        Original PDF — {meta.invoice_number || 'Invoice'}
      </div>
      <div className="pdf-body">
        <h3>PURCHASE INVOICE</h3>
        <div className="co">
          {meta.vendor || 'Vendor'}<br/>
          {meta.invoice_date || ''}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
          <span>{meta.invoice_number}</span>
          <span>{meta.invoice_date}</span>
        </div>
        <hr/>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Item</th>
              <th style={{ textAlign: 'right' }}>Qty</th>
              <th style={{ textAlign: 'right' }}>Rate</th>
              <th style={{ textAlign: 'right' }}>Disc%</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 12).map((r, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td style={{ fontSize: 9 }}>{r.extractedName}</td>
                <td style={{ textAlign: 'right' }}>{r.qty}</td>
                <td style={{ textAlign: 'right' }}>{Number(r.rate).toFixed(2)}</td>
                <td style={{ textAlign: 'right', color: 'var(--warn)' }}>{r.discPct > 0 ? `${r.discPct}%` : '—'}</td>
              </tr>
            ))}
            {rows.length > 12 && (
              <tr>
                <td colSpan="4" style={{ textAlign: 'center', color: '#999', padding: '8px 0' }}>
                  … {rows.length - 12} more items …
                </td>
              </tr>
            )}
            <tr className="total-row">
              <td colSpan="3">TOTAL</td>
              <td style={{ textAlign: 'right' }}>
                {formatINR(rows.reduce((s, r) => s + (Number(r.qty) * Number(r.rate)), 0))}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ——— Map API item to internal row ———
function itemToRow(item, i) {
  // Map API status names to design status names
  const statusMap = { normal: 'ok', price_change: 'price-changed', new_product: 'new-product' };
  return {
    uid: `r${i}`,
    index: item.index ?? i + 1,
    extractedName: item.product_name,
    mappedId: item.zoho_item_id ?? null,
    zohoItemName: item.zoho_item_name ?? null,
    qty: Number(item.qty) || 0,
    rate: Number(item.rate) || 0,
    amount: Number(item.amount) || 0,
    discPct: Number(item.disc_pct) || 0,
    cgstPct: Number(item.cgst_pct) || 0,
    sgstPct: Number(item.sgst_pct) || 0,
    candidates: item.candidates ?? [],
    apiStatus: statusMap[item.status] ?? 'ok',
    isNew: item.status === 'new_product',
    priceDetail: item.price_detail ?? {},
    mapped: !!item.mapped,
    newName: null,
  };
}

// ——— Main Review Screen ———
export default function ReviewPage({ data, onReset, onConfirmed, onToast }) {
  const { meta, items: initialItems, file_path } = data;

  const [rows, setRows] = useState(() =>
    initialItems.map((item, i) => itemToRow(item, i))
  );
  const [pickerOpenFor, setPickerOpenFor] = useState(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [editingUid, setEditingUid] = useState(null);
  const [showPdf, setShowPdf] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Build a deduplicated product list from all candidates across all rows
  const masterProducts = useMemo(() => {
    const seen = new Set();
    const products = [];
    for (const row of rows) {
      for (const c of (row.candidates || [])) {
        if (!seen.has(c.zoho_item_id)) {
          seen.add(c.zoho_item_id);
          products.push({
            id: c.zoho_item_id,
            name: c.zoho_item_name,
            sku: c.sku || null,
            score: c.score ?? null,
            lastRate: null,
          });
        }
      }
    }
    // If we have candidates, they are already sorted by score. 
    // masterProducts is a fallback, but let's sort it by name for consistency if used.
    return products.sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  // Compute effective status for a row
  const statusOf = useCallback((row) => {
    if (!row.mappedId) return 'unmapped';
    if (row.isNew) return 'new-product';
    const prevRate = row.priceDetail?.previous_rate;
    if (prevRate != null && Math.abs(row.rate - prevRate) > 0.01) return 'price-changed';
    return row.apiStatus === 'price-changed' ? 'price-changed' : 'ok';
  }, []);

  // Enrich rows with computed status
  const enriched = rows.map(r => ({ ...r, _status: statusOf(r) }));

  const counts = {
    all: enriched.length,
    ok: enriched.filter(r => r._status === 'ok').length,
    'price-changed': enriched.filter(r => r._status === 'price-changed').length,
    'new-product': enriched.filter(r => r._status === 'new-product' || r._status === 'unmapped').length,
  };

  const filtered = enriched.filter(r => {
    if (filter === 'ok' && r._status !== 'ok') return false;
    if (filter === 'price-changed' && r._status !== 'price-changed') return false;
    if (filter === 'new-product' && r._status !== 'new-product' && r._status !== 'unmapped') return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      const name = (r.zohoItemName || r.extractedName).toLowerCase();
      if (!name.includes(q)) return false;
    }
    return true;
  });

  const updateRow = (uid, patch) =>
    setRows(rows => rows.map(r => r.uid === uid ? { ...r, ...patch } : r));

  const removeRow = (uid) =>
    setRows(rows => rows.filter(r => r.uid !== uid));

  const mapTo = (row, product) => {
    updateRow(row.uid, {
      mappedId: product.id,
      zohoItemName: product.name,
      isNew: false,
      apiStatus: 'ok',
    });
    // Persist mapping asynchronously
    saveMapping(row.extractedName, product.id, product.name).catch(() => {});
  };

  const createNew = (row, name) => {
    updateRow(row.uid, {
      mappedId: `new-${row.uid}`,
      isNew: true,
      newName: name,
      zohoItemName: name,
    });
  };

  // ——— Totals computation ———
  const computed = enriched.map(r => {
    const qty = Number(r.qty) || 0;
    const rate = Number(r.rate) || 0;
    const gross = qty * rate;
    const disc = gross * ((Number(r.discPct) || 0) / 100);
    const taxable = gross - disc;
    const cgst = taxable * ((Number(r.cgstPct) || 0) / 100);
    const sgst = taxable * ((Number(r.sgstPct) || 0) / 100);
    const lineTotal = taxable + cgst + sgst;
    return { ...r, _gross: gross, _disc: disc, _cgst: cgst, _sgst: sgst, _lineTotal: lineTotal };
  });

  const grossTotal    = computed.reduce((s, r) => s + r._gross, 0);
  const totalDiscount = computed.reduce((s, r) => s + r._disc, 0);
  const totalCgst     = computed.reduce((s, r) => s + r._cgst, 0);
  const totalSgst     = computed.reduce((s, r) => s + r._sgst, 0);
  const grandTotal    = computed.reduce((s, r) => s + r._lineTotal, 0);

  const unmappedCount    = enriched.filter(r => r._status === 'unmapped').length;
  const priceChangedCount = counts['price-changed'];
  const newCount         = enriched.filter(r => r._status === 'new-product').length;

  // ——— Sync handler ———
  async function handleSync() {
    setSyncing(true);
    try {
      const res = await syncZohoItems();
      onToast('success', 'Sync complete', `${res.synced_items} items cached from Zoho Books.`);
    } catch (e) {
      onToast('error', 'Sync failed', e.message);
    } finally {
      setSyncing(false);
    }
  }

  // ——— Confirm handler ———
  async function handleConfirm() {
    if (unmappedCount > 0) {
      onToast('error', 'Unmapped products',
        `Map all ${unmappedCount} unmatched product(s) before confirming.`);
      return;
    }
    setConfirming(true);
    try {
      const activeRows = rows.filter(r => statusOf(r) !== 'removed');
      const res = await confirmInvoice({
        invoice_number: meta.invoice_number ?? 'UNKNOWN',
        invoice_date:   meta.invoice_date   ?? new Date().toISOString().slice(0, 10),
        vendor_zoho_id: null,
        file_path:      file_path,
        line_items: activeRows.map(r => ({
          index:         r.index,
          product_name:  r.extractedName,
          zoho_item_id:  r.mappedId,
          zoho_item_name: r.zohoItemName,
          qty:           r.qty,
          rate:          r.rate,
          amount:        r.amount,
          cgst_pct:      r.cgstPct,
          sgst_pct:      r.sgstPct,
          disc_pct:      r.discPct,
        })),
      });

      onConfirmed({
        invoice_number: meta.invoice_number,
        zoho_bill_id:   res.zoho_bill_id,
        grand_total:    grandTotal,
        item_count:     activeRows.length,
      });
    } catch (e) {
      onToast('error', 'Confirmation failed', e.message);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className={`review-wrap ${showPdf ? 'with-preview' : ''}`}>

      {/* ——— Metadata card ——— */}
      <div className="meta-card">
        <div className="meta-field">
          <label>Vendor</label>
          <div className="val vendor-val">{meta.vendor || 'Milky Mist Dairy Food Limited'}</div>
          {meta.vendor_gst && (
            <div className="meta-sub">GST {meta.vendor_gst}</div>
          )}
        </div>
        <div className="meta-field">
          <label>Invoice No.</label>
          <div className="val num">{meta.invoice_number || '—'}</div>
          {meta.company_invoice && (
            <div className="meta-sub">{meta.company_invoice}</div>
          )}
        </div>
        <div className="meta-field">
          <label>Invoice Date</label>
          <div className="val">{meta.invoice_date || '—'}</div>
        </div>
        <div className="meta-field" style={{ textAlign: 'right' }}>
          <label>Total Amount</label>
          <div className="val total-val num">{formatINR(grandTotal)}</div>
        </div>
      </div>

      <div className={`main-grid ${showPdf ? 'with-preview' : ''}`}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>

          {/* ——— Table toolbar ——— */}
          <div className="table-toolbar">
            <div className="table-title">
              Line items
              <span className="table-count">· {filtered.length} of {rows.length}</span>
            </div>

            <FilterChip active={filter === 'all'} onClick={() => setFilter('all')}>
              All <span style={{ opacity: .6 }}>{counts.all}</span>
            </FilterChip>
            <FilterChip active={filter === 'ok'} onClick={() => setFilter('ok')}>
              <span className="dot" style={{ background: 'var(--ok)', width: 7, height: 7, borderRadius: '50%', display: 'inline-block' }}/>
              {' '}OK <span style={{ opacity: .6 }}>{counts.ok}</span>
            </FilterChip>
            <FilterChip active={filter === 'price-changed'} onClick={() => setFilter('price-changed')}>
              <span className="dot" style={{ background: 'var(--warn)', width: 7, height: 7, borderRadius: '50%', display: 'inline-block' }}/>
              {' '}Price changed <span style={{ opacity: .6 }}>{counts['price-changed']}</span>
            </FilterChip>
            <FilterChip active={filter === 'new-product'} onClick={() => setFilter('new-product')}>
              <span className="dot" style={{ background: 'var(--err)', width: 7, height: 7, borderRadius: '50%', display: 'inline-block' }}/>
              {' '}New / unmapped <span style={{ opacity: .6 }}>{counts['new-product']}</span>
            </FilterChip>

            <div className="toolbar-spacer"/>

            <div className="search-wrap">
              <Icon.search size={14}/>
              <input
                className="search-input"
                placeholder="Search items…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          {/* ——— Table ——— */}
          <div className="table-card">
            <div className="table-scroll">
              <table className="items">
                <thead>
                  <tr>
                    <th className="col-idx">#</th>
                    <th className="col-product">Product</th>
                    <th className="col-qty num-col">Qty</th>
                    <th className="col-rate num-col">Rate</th>
                    <th className="col-disc num-col">Disc.</th>
                    <th className="col-tax num-col">GST</th>
                    <th className="col-total num-col">Total</th>
                    <th className="col-status">Status</th>
                    <th className="col-action center"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => {
                    const c = computed.find(x => x.uid === row.uid);
                    const isEditing = editingUid === row.uid;
                    const prevRate = row.priceDetail?.previous_rate;

                    const rowCls = [
                      (row._status === 'new-product' || row._status === 'unmapped') ? 'row-err' :
                        row._status === 'price-changed' ? 'row-warn' : '',
                      isEditing ? 'row-editing' : '',
                    ].filter(Boolean).join(' ');

                    const displayName = row.isNew
                      ? (row.newName || row.extractedName)
                      : (row.zohoItemName || row.extractedName);

                    const lineTotal = c ? c._lineTotal : (Number(row.rate) * Number(row.qty));
                    const rowIdx = rows.findIndex(r => r.uid === row.uid) + 1;

                    return (
                      <tr key={row.uid} className={rowCls}>
                        <td className="col-idx num">{rowIdx}</td>

                        {/* Product cell */}
                        <td className="col-product">
                          <div className="product-cell">
                            {isEditing || row._status === 'unmapped' ? (
                              <button
                                className={`product-select ${row._status === 'unmapped' ? 'needs-map' : ''}`}
                                onClick={() => setPickerOpenFor(row.uid)}
                              >
                                <div className="product-text">
                                  <div className="product-name">
                                    {row._status === 'unmapped' ? '⚠ Select a product' : displayName}
                                  </div>
                                  <div className="product-brand">
                                    {row._status === 'unmapped'
                                      ? <span>From invoice: <i>{row.extractedName}</i></span>
                                      : <span className="num">{row.extractedName}</span>
                                    }
                                  </div>
                                </div>
                                <span className="chev"><Icon.chev/></span>
                              </button>
                            ) : (
                              <div className={`product-select readonly ${row._status === 'unmapped' ? 'needs-map' : ''}`}>
                                <div className="product-text">
                                  <div className="product-name">
                                    {row._status === 'unmapped' ? '⚠ Select a product' : displayName}
                                  </div>
                                  <div className="product-brand">
                                    {row._status === 'unmapped'
                                      ? <span>From invoice: <i>{row.extractedName}</i></span>
                                      : <span className="num">{row.extractedName}</span>
                                    }
                                  </div>
                                </div>
                              </div>
                            )}
                            {pickerOpenFor === row.uid && (
                              <ProductPicker
                                row={row}
                                products={(row.candidates || []).map(c => ({
                                  id: c.zoho_item_id,
                                  name: c.zoho_item_name,
                                  sku: c.sku,
                                  score: c.score,
                                })) || masterProducts}
                                onSelect={(p) => mapTo(row, p)}
                                onCreateNew={(name) => createNew(row, name)}
                                onClose={() => setPickerOpenFor(null)}
                              />
                            )}
                          </div>
                        </td>

                        {/* Qty */}
                        <td className="col-qty num-col">
                          {isEditing ? (
                            <input
                              type="number"
                              className="cell-input num"
                              value={row.qty}
                              onChange={(e) => updateRow(row.uid, { qty: Number(e.target.value) || 0 })}
                            />
                          ) : (
                            <span className="cell-readonly">{row.qty}</span>
                          )}
                        </td>

                        {/* Rate */}
                        <td className="col-rate num-col">
                          <div className="rate-wrap">
                            {row._status === 'price-changed' && prevRate != null && (
                              <span className="tip-wrap" tabIndex={0}>
                                <span className="rate-prev num">{formatINR(prevRate)}</span>
                                <div className="tip">
                                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Rate changed</div>
                                  <div className="tip-row">
                                    <span className="k">Previous</span>
                                    <span className="v">{formatINR(prevRate)}</span>
                                  </div>
                                  <div className="tip-row">
                                    <span className="k">Current</span>
                                    <span className={`v ${row.rate > prevRate ? 'up' : 'down'}`}>
                                      {formatINR(row.rate)}
                                    </span>
                                  </div>
                                  <div className="tip-delta tip-row">
                                    <span className="k">Change</span>
                                    <span className={`v ${row.rate > prevRate ? 'up' : 'down'}`}>
                                      {row.rate > prevRate ? '+' : ''}
                                      {(((row.rate - prevRate) / prevRate) * 100).toFixed(1)}%
                                    </span>
                                  </div>
                                </div>
                              </span>
                            )}
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                className={`cell-input num ${row._status === 'price-changed' ? 'changed' : ''}`}
                                style={{ maxWidth: row._status === 'price-changed' ? 96 : '100%' }}
                                value={row.rate}
                                onChange={(e) => updateRow(row.uid, { rate: Number(e.target.value) || 0 })}
                              />
                            ) : (
                              <span
                                className="cell-readonly"
                                style={{
                                  color: row._status === 'price-changed' ? 'var(--warn)' : 'var(--ink)',
                                  fontWeight: row._status === 'price-changed' ? 600 : 400,
                                }}
                              >
                                {Number(row.rate).toFixed(2)}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Discount */}
                        <td className="col-disc num-col">
                          {isEditing ? (
                            <input
                              type="number"
                              step="0.01"
                              className="cell-input num"
                              value={row.discPct || 0}
                              onChange={(e) => updateRow(row.uid, { discPct: Number(e.target.value) || 0 })}
                            />
                          ) : (
                            <span className={`disc-pill ${(row.discPct || 0) === 0 ? 'zero' : ''}`}>
                              {(row.discPct || 0) === 0 ? '—' : `−${Number(row.discPct).toFixed(2)}%`}
                            </span>
                          )}
                        </td>

                        {/* GST */}
                        <td className={`col-tax num-col tax-cell ${(row.cgstPct || 0) === 0 ? 'zero' : ''}`}>
                          {(row.cgstPct || 0) === 0 ? '—' : `${((row.cgstPct || 0) + (row.sgstPct || 0)).toFixed(0)}%`}
                        </td>

                        {/* Total */}
                        <td className="col-total num-col num" style={{ fontWeight: 500 }}>
                          {formatINR(lineTotal)}
                        </td>

                        {/* Status badge */}
                        <td className="col-status">
                          <Badge status={row._status}/>
                        </td>

                        {/* Row actions: Edit + Delete */}
                        <td className="col-action center">
                          <div className="row-actions">
                            <button
                              className={`action-btn ${isEditing ? 'edit-active' : 'primary'}`}
                              onClick={() => {
                                setEditingUid(isEditing ? null : row.uid);
                                if (isEditing) setPickerOpenFor(null);
                              }}
                              title={isEditing ? 'Done editing' : 'Edit row'}
                            >
                              {isEditing ? <Icon.check size={15}/> : <Icon.pencil/>}
                            </button>
                            <button
                              className="action-btn danger"
                              onClick={() => removeRow(row.uid)}
                              title="Remove row"
                            >
                              <Icon.trash/>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* ——— Totals breakdown card ——— */}
          <div className="totals-card">
            <div className="k">Gross amount</div>
            <div className="v num">{formatINR(grossTotal)}</div>

            {totalDiscount > 0 && <>
              <div className="k">Total discount</div>
              <div className="v num neg">− {formatINR(totalDiscount)}</div>
            </>}

            {totalCgst > 0 && <>
              <div className="k">CGST</div>
              <div className="v num">{formatINR(totalCgst)}</div>
            </>}

            {totalSgst > 0 && <>
              <div className="k">SGST</div>
              <div className="v num">{formatINR(totalSgst)}</div>
            </>}

            {totalCgst === 0 && totalSgst === 0 && (
              <><div className="k">GST</div><div className="v num">—</div></>
            )}

            <div className="divider"/>
            <div className="k grand-k">Total (incl. tax)</div>
            <div className="v num grand-v">{formatINR(grandTotal)}</div>
          </div>
        </div>

        {/* PDF side panel */}
        {showPdf && <PdfPreviewPanel meta={meta} rows={rows}/>}
      </div>

      {/* ——— Fixed bottom action bar ——— */}
      <div className="action-bar">
        <div className="action-bar-summary">
          <div className="summary-item">
            Items: <span className="n">{rows.length}</span>
          </div>
          <div className="summary-item">
            Gross: <span className="n">{formatINR(grossTotal)}</span>
          </div>
          <div className="summary-item" style={{ color: 'var(--ok)' }}>
            Disc: <span className="n">−{formatINR(totalDiscount)}</span>
          </div>
          <div className="summary-item">
            Tax: <span className="n">{formatINR(totalCgst + totalSgst)}</span>
          </div>
          <div className="summary-item">
            Total: <span className="n" style={{ fontSize: 15 }}>{formatINR(grandTotal)}</span>
          </div>
          {priceChangedCount > 0 && (
            <div className="summary-item" style={{ color: 'var(--warn)' }}>
              <Icon.warn size={14}/>
              <span className="n">{priceChangedCount}</span>{' '}
              price {priceChangedCount === 1 ? 'change' : 'changes'}
            </div>
          )}
        </div>

        <div className="action-bar-spacer"/>

        {unmappedCount > 0 && (
          <div className="blocker">
            <Icon.warn size={14}/>
            {unmappedCount} item{unmappedCount > 1 ? 's' : ''} need{unmappedCount === 1 ? 's' : ''} mapping
          </div>
        )}

        <button className="btn btn-ghost" onClick={onReset}>
          <Icon.back/> Back
        </button>

        <button
          className="btn btn-primary btn-lg"
          disabled={unmappedCount > 0 || confirming}
          onClick={handleConfirm}
        >
          {confirming
            ? <><Icon.sync size={16}/> Creating bill…</>
            : <><Icon.check size={16}/> Confirm &amp; create bill</>
          }
        </button>
      </div>
    </div>
  );
}
