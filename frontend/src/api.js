// API base URL — default to empty string to use Nginx proxy
const BASE = import.meta.env.VITE_API_URL ?? '';

export async function uploadInvoice(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload-invoice/`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Upload failed');
  }
  return res.json();
}

export async function processInvoice(text, filePath) {
  const res = await fetch(`${BASE}/process-invoice/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, file_path: filePath }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Processing failed');
  }
  return res.json();
}

export async function confirmInvoice(payload) {
  const res = await fetch(`${BASE}/confirm-invoice/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Confirmation failed');
  }
  return res.json();
}

export async function saveMapping(vendorProductName, zohoItemId, zohoItemName) {
  const res = await fetch(`${BASE}/mappings/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      vendor_product_name: vendorProductName,
      zoho_item_id: zohoItemId,
      zoho_item_name: zohoItemName,
    }),
  });
  if (!res.ok) throw new Error('Failed to save mapping');
  return res.json();
}

export async function syncZohoItems() {
  const res = await fetch(`${BASE}/zoho/sync-items/`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Sync failed');
  }
  return res.json();
}
