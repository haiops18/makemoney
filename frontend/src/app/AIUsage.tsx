import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { z } from 'zod';

const breakdown = z.object({ key: z.string(), invocations: z.number(), input_tokens: z.number(), output_tokens: z.number(), calculated_cost: z.string(), confirmed_cost: z.string() });
const item = z.object({
  id: z.string().uuid(), task_type: z.string(), agent_role: z.string(), provider_name: z.string(), provider_kind: z.string(), model_id: z.string(),
  status: z.string(), error_code: z.string().nullable(), input_tokens: z.number().nullable(), output_tokens: z.number().nullable(),
  estimated_cost: z.string(), calculated_cost: z.string().nullable(), confirmed_cost: z.string().nullable(), reservation_id: z.string().uuid(),
  reservation_status: z.string(), held_amount: z.string(), needs_reconciliation: z.boolean(), created_at: z.string(),
});
const usage = z.object({
  currency: z.literal('USD'), invocations: z.number(), by_status: z.record(z.string(), z.number()), input_tokens: z.number(), output_tokens: z.number(),
  estimated_cost: z.string(), calculated_cost: z.string(), confirmed_cost: z.string(), held_amount: z.string(), needs_reconciliation: z.number(),
  by_role: z.array(breakdown), by_model: z.array(breakdown), items: z.array(item), total_items: z.number(),
});

const money = /^\d{1,12}(?:\.\d{1,6})?$/;

function Reconcile({ token, reservationId, held, vi }: { token: string; reservationId: string; held: string; vi: boolean }) {
  const tr = (a: string, b: string) => vi ? a : b; const cache = useQueryClient(); const retry = useRef<{ signature: string; key: string } | null>(null);
  const [amount, setAmount] = useState(''); const [reason, setReason] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function close(outcome: 'settle' | 'release') {
    if (!money.test(amount) || !reason.trim()) { setError(tr('Nhập số tiền thực tế (USD) và lý do.', 'Enter the actual USD amount and a reason.')); return; }
    if (!window.confirm(tr('Ghi nhận chi phí thực tế này? Không thể hoàn tác.', 'Record this actual cost? This cannot be undone.'))) return;
    setBusy(true); setError('');
    try {
      const body = JSON.stringify({ actual_amount: amount, reason: reason.trim() }); const signature = `${outcome}:${body}`;
      if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/budgets/reservations/${reservationId}/${outcome}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': retry.current.key }, body });
      if (!response.ok) { const detail = await response.json().catch(() => null) as { detail?: unknown } | null; throw new Error(typeof detail?.detail === 'string' ? detail.detail : `API ${response.status}`); }
      retry.current = null; await Promise.all([cache.invalidateQueries({ queryKey: ['ai-usage'] }), cache.invalidateQueries({ queryKey: ['budget'] })]);
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể đối soát.', 'Unable to reconcile.')); } finally { setBusy(false); }
  }
  return <div className="toolbar"><label className="field">{tr('Chi phí thực tế (USD)', 'Actual cost (USD)')}<input inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} placeholder={held}/></label>
    <label className="field">{tr('Lý do / nguồn hóa đơn', 'Reason / invoice reference')}<input value={reason} onChange={event => setReason(event.target.value)} maxLength={500}/></label>
    <button type="button" disabled={busy} onClick={() => void close('settle')}>{tr('Xác nhận chi phí', 'Settle')}</button>
    <button type="button" disabled={busy || (money.test(amount) && Number(amount) > Number(held))} onClick={() => void close('release')}>{tr('Giải phóng phần dư', 'Release remainder')}</button>
    {error && <p role="alert">{error}</p>}</div>;
}

export default function AIUsage({ token }: { token: string }) {
  const { i18n } = useTranslation(); const vi = i18n.language.startsWith('vi'); const tr = (a: string, b: string) => vi ? a : b;
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ['ai-usage', offset], enabled: !!token, queryFn: async () => {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/usage?limit=25&offset=${offset}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return usage.parse(await response.json());
  } });
  const data = query.data;
  const cards: [string, string][] = data ? [[tr('Lượt gọi AI', 'AI invocations'), String(data.invocations)], [tr('Ước tính theo token', 'Token-based estimate'), `${data.calculated_cost} USD`],
    [tr('Đã xác nhận', 'Confirmed'), `${data.confirmed_cost} USD`], [tr('Đang giữ ngân sách', 'Budget held'), `${data.held_amount} USD`],
    [tr('Cần đối soát', 'Needs reconciliation'), String(data.needs_reconciliation)], ['Tokens', `${data.input_tokens} / ${data.output_tokens}`]] : [];
  return <section><div className="page-head"><div><h1>{tr('Chi phí AI', 'AI usage')}</h1>
    <p>{tr('Chi phí theo token chỉ là ước tính. Chỉ khoản đã đối soát với hóa đơn provider mới là chi phí xác nhận. Lượt gọi không rõ kết quả vẫn giữ ngân sách.', 'Token-based cost is only an estimate; only amounts reconciled against the provider invoice are confirmed. Invocations with unknown outcomes keep their budget hold.')}</p></div></div>
    {!token && <p>{tr('Vui lòng đăng nhập Owner.', 'Sign in as Owner.')}</p>}
    {query.isLoading && <p role="status">{tr('Đang tải…', 'Loading…')}</p>}
    {query.error && <p role="alert">{tr('Không thể tải chi phí AI.', 'Unable to load AI usage.')} <button onClick={() => void query.refetch()}>{tr('Thử lại', 'Retry')}</button></p>}
    {data && <><div className="kpis">{cards.map(([label, value]) => <article className="card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</div>
      {data.invocations === 0 ? <p>{tr('Chưa có lượt gọi AI nào.', 'No AI invocations yet.')}</p> : <>
        <h2>{tr('Theo agent', 'By agent')}</h2><div className="table">{data.by_role.map(row => <div className="row" key={row.key}><b>{row.key}</b><span>{row.invocations}</span><span>{row.input_tokens} / {row.output_tokens}</span><span>{row.calculated_cost} · {row.confirmed_cost} USD</span></div>)}</div>
        <h2>{tr('Theo model', 'By model')}</h2><div className="table">{data.by_model.map(row => <div className="row" key={row.key}><b>{row.key}</b><span>{row.invocations}</span><span>{row.input_tokens} / {row.output_tokens}</span><span>{row.calculated_cost} · {row.confirmed_cost} USD</span></div>)}</div>
        <h2>{tr('Lượt gọi', 'Invocations')}</h2><div className="table">{data.items.map(row => <div className="row" key={row.id}><div><b>{row.task_type}</b><small>{row.provider_name} · {row.model_id} · {new Date(row.created_at).toLocaleString(vi ? 'vi-VN' : 'en-US', { timeZone: 'Asia/Ho_Chi_Minh' })}</small></div>
          <span>{row.status}{row.error_code ? ` · ${row.error_code}` : ''}</span><span>{row.input_tokens ?? '—'} / {row.output_tokens ?? '—'}</span>
          <span>{tr('Ước tính', 'Estimate')} {row.calculated_cost ?? row.estimated_cost} · {tr('Xác nhận', 'Confirmed')} {row.confirmed_cost ?? '—'} · {tr('Giữ', 'Held')} {row.held_amount}</span>
          <span>{row.needs_reconciliation ? tr('Cần đối soát', 'Needs reconciliation') : row.reservation_status}</span>
          {row.needs_reconciliation && <Reconcile token={token} reservationId={row.reservation_id} held={row.held_amount} vi={vi}/>}</div>)}</div>
        <div className="toolbar"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 25))}>{tr('Trước', 'Previous')}</button><span>{data.total_items}</span><button disabled={offset + 25 >= data.total_items} onClick={() => setOffset(offset + 25)}>{tr('Tiếp', 'Next')}</button></div>
        <p>{tr('Ngân sách tháng hiển thị tại', 'The monthly budget is shown in')} <Link to="/finance">{tr('Tài chính & Ngân sách', 'Finance & Budget')}</Link>.</p></>}</>}
  </section>;
}
