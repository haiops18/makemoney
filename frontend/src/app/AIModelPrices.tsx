import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

const price = z.object({ id: z.string().uuid(), model_id: z.string(), version: z.string(), input_per_million: z.string(), output_per_million: z.string(), currency: z.literal('USD'), effective_at: z.string(), expires_at: z.string().nullable(), source_note: z.string() });
const form = z.object({ model_id: z.string().trim().min(1).max(200), version: z.string().trim().min(1).max(100), input_per_million: z.string().regex(/^\d{1,12}(?:\.\d{1,6})?$/), output_per_million: z.string().regex(/^\d{1,12}(?:\.\d{1,6})?$/), effective_at: z.string().datetime(), source_note: z.string().trim().min(1).max(500) });

export default function AIModelPrices({ token, providerId, defaultModel }: { token: string; providerId: string; defaultModel: string }) {
  const { i18n } = useTranslation(); const vi = i18n.language.startsWith('vi'); const tr = (a: string, b: string) => vi ? a : b;
  const cache = useQueryClient(); const pending = useRef<{ signature: string; key: string } | null>(null);
  const [model, setModel] = useState(defaultModel); const [version, setVersion] = useState(''); const [inputCost, setInputCost] = useState(''); const [outputCost, setOutputCost] = useState(''); const [effective, setEffective] = useState(''); const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [success, setSuccess] = useState('');
  const url = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/providers/${providerId}/prices`;
  const query = useQuery({ queryKey: ['ai-prices', providerId], queryFn: async () => { const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error(`API ${response.status}`); return z.array(price).parse(await response.json()); } });
  async function save() {
    setError(''); setSuccess('');
    const date = new Date(effective); const parsed = form.safeParse({ model_id: model, version, input_per_million: inputCost, output_per_million: outputCost, effective_at: Number.isNaN(date.getTime()) ? '' : date.toISOString(), source_note: note });
    if (!parsed.success) { setError(tr('Kiểm tra giá, thời điểm và nguồn.', 'Check prices, effective time and source.')); return; }
    setBusy(true);
    try { const body = JSON.stringify(parsed.data); if (pending.current?.signature !== body) pending.current = { signature: body, key: crypto.randomUUID() };
      const response = await fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': pending.current.key }, body });
      if (!response.ok) throw new Error(`API ${response.status}`); price.parse(await response.json()); pending.current = null;
      await cache.invalidateQueries({ queryKey: ['ai-prices', providerId] }); setSuccess(tr('Đã lưu phiên bản giá.', 'Price version saved.'));
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể lưu giá.', 'Unable to save price.')); } finally { setBusy(false); }
  }
  return <section className="panel"><h3>{tr('Giá model do Owner nhập', 'Owner-entered model prices')}</h3><p>{tr('Giá cần được kiểm chứng; lưu giá không cấp quyền chạy AI.', 'Prices require verification; saving a price does not authorize AI execution.')}</p>
    <form onSubmit={event => { event.preventDefault(); void save(); }}><label className="field">{tr('Model ID của giá', 'Price model ID')}<input value={model} onChange={event => setModel(event.target.value)} maxLength={200} required/></label>
      <label className="field">{tr('Phiên bản giá', 'Price version')}<input value={version} onChange={event => setVersion(event.target.value)} maxLength={100} required/></label>
      <label className="field">{tr('USD / 1 triệu input token', 'USD / 1M input tokens')}<input type="number" min="0" step="0.000001" value={inputCost} onChange={event => setInputCost(event.target.value)} required/></label>
      <label className="field">{tr('USD / 1 triệu output token', 'USD / 1M output tokens')}<input type="number" min="0" step="0.000001" value={outputCost} onChange={event => setOutputCost(event.target.value)} required/></label>
      <label className="field">{tr('Hiệu lực từ (giờ thiết bị)', 'Effective from (device time)')}<input type="datetime-local" value={effective} onChange={event => setEffective(event.target.value)} required/></label>
      <label className="field">{tr('Ghi chú nguồn giá', 'Pricing source note')}<input value={note} onChange={event => setNote(event.target.value)} maxLength={500} required/></label><button disabled={busy}>{tr('Lưu giá', 'Save price')}</button></form>
    {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}{query.isLoading && <p>{tr('Đang tải…', 'Loading…')}</p>}{query.error && <p role="alert">{tr('Không thể tải giá.', 'Unable to load prices.')}</p>}
    {query.data?.length === 0 && <p>{tr('Chưa có giá.', 'No prices configured.')}</p>}{query.data?.map(item => <p key={item.id}>{item.model_id} · {item.version} · {item.input_per_million}/{item.output_per_million} USD · {new Date(item.effective_at).toLocaleString(vi ? 'vi-VN' : 'en-US', { timeZone: 'Asia/Ho_Chi_Minh' })} · {item.source_note}</p>)}
  </section>;
}
