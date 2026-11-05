import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

const control = z.object({ id: z.string().uuid(), enabled: z.boolean(), version: z.number(), execution_available: z.boolean() });
const policy = z.object({ id: z.string().uuid(), enabled: z.boolean(), rules_json: z.object({ allowed_action_types: z.array(z.string()), ai_inference_allowed: z.boolean().optional(), external_execution: z.boolean() }) });
const prepared = z.object({ action: z.object({ policy_id: z.string().uuid(), action_type: z.literal('AI_CONTROL_ENABLE'), action_payload: z.record(z.string(), z.unknown()), resource_type: z.string(), resource_id: z.string().uuid(), scope: z.literal('ONCE') }), action_hash: z.string() });
const approval = z.object({ id: z.string().uuid(), status: z.string(), action_hash: z.string(), resource_id: z.string() });

export default function AIConsent({ token }: { token: string }) {
  const { i18n } = useTranslation(); const vi = i18n.language.startsWith('vi'); const tr = (a: string, b: string) => vi ? a : b;
  const cache = useQueryClient(); const retry = useRef<{ signature: string; key: string } | null>(null);
  const approvalDraft = useRef<{ hash: string; expiresAt: string } | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [success, setSuccess] = useState('');
  const base = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1`;
  async function request(path: string, init?: RequestInit): Promise<unknown> { const response = await fetch(`${base}${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...init?.headers } }); if (!response.ok) throw new Error(`API ${response.status}`); return response.json(); }
  const state = useQuery({ queryKey: ['ai-control'], enabled: !!token, queryFn: async () => control.parse(await request('/ai/control')) });
  const policies = useQuery({ queryKey: ['ai-control-policies'], enabled: !!token, queryFn: async () => z.array(policy).parse(await request('/policies')) });
  const policyId = policies.data?.find(item => item.enabled && item.rules_json.allowed_action_types.includes('AI_CONTROL_ENABLE') && item.rules_json.ai_inference_allowed === true && item.rules_json.external_execution === false)?.id;
  const action = useQuery({ queryKey: ['ai-control-action', policyId, state.data?.version], enabled: !!token && !!policyId && !!state.data && !state.data.enabled, queryFn: async () => prepared.parse(await request(`/ai/control/enable-action?policy_id=${policyId}`)) });
  const approvals = useQuery({ queryKey: ['ai-control-approvals'], enabled: !!token && !!state.data && !state.data.enabled, queryFn: async () => z.object({ items: z.array(approval) }).parse(await request('/approvals')), refetchInterval: 5000 });
  const approved = approvals.data?.items.find(item => item.status === 'APPROVED' && item.action_hash === action.data?.action_hash && item.resource_id === state.data?.id);
  async function post(path: string, body: Record<string, unknown>, resultSchema: z.ZodType) {
    setBusy(true); setError(''); setSuccess('');
    try { const serialized = JSON.stringify(body); const signature = `${path}:${serialized}`; if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      resultSchema.parse(await request(path, { method: 'POST', headers: { 'Idempotency-Key': retry.current.key }, body: serialized })); retry.current = null; if (path === '/approvals') approvalDraft.current = null;
      await Promise.all([cache.invalidateQueries({ queryKey: ['ai-control'] }), cache.invalidateQueries({ queryKey: ['ai-control-action'] }), cache.invalidateQueries({ queryKey: ['ai-control-approvals'] })]); setSuccess(tr('Backend đã xác nhận.', 'Backend confirmed the change.'));
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể lưu.', 'Unable to save.')); } finally { setBusy(false); }
  }
  if (!token) return null;
  return <section className="panel"><h2>{tr('Quyền AI toàn cục', 'Global AI consent')}</h2><p>{tr('Quyền toàn cục không phê duyệt tác vụ hoặc ngân sách. Khi bật, mỗi task AI vẫn cần phê duyệt riêng và giữ ngân sách trước khi chạy.', 'Global consent does not approve individual tasks or budgets. When enabled, each AI task still needs its own approval and a budget hold before it runs.')}</p>
    {state.isLoading && <p>{tr('Đang tải…', 'Loading…')}</p>}{(state.error || policies.error || action.error || approvals.error) && <p role="alert">{tr('Không thể tải kiểm soát AI.', 'Unable to load AI controls.')}</p>}
    {state.data && <><p>{tr('Quyền Owner', 'Owner consent')}: {state.data.enabled ? tr('Đã bật', 'Enabled') : tr('Đã tắt', 'Disabled')} · {tr('Thực thi AI', 'AI execution')}: {state.data.execution_available ? tr('Có thể yêu cầu theo từng task', 'Requestable per approved task') : tr('Chưa khả dụng', 'Unavailable')}</p>
      {!state.data.enabled && <><button disabled={busy || !action.data} onClick={() => { if (!action.data || !window.confirm(tr('Tạo yêu cầu phê duyệt quyền AI?', 'Request approval for AI consent?'))) return; if (approvalDraft.current?.hash !== action.data.action_hash) approvalDraft.current = { hash: action.data.action_hash, expiresAt: new Date(Date.now() + 15 * 60000).toISOString() }; const body = { ...action.data.action, expires_at: approvalDraft.current.expiresAt, reason: tr('Owner xem xét quyền AI toàn cục', 'Owner review of global AI consent') }; void post('/approvals', body, approval); }}>{tr('Yêu cầu phê duyệt quyền AI', 'Request AI consent approval')}</button>
        <p>{tr('Phê duyệt yêu cầu trong Approval Center, sau đó xác nhận bên dưới.', 'Approve the request in Approval Center, then confirm below.')}</p><button disabled={busy || !approved || !policyId} onClick={() => { if (approved && policyId && window.confirm(tr('Bật quyền AI sau phê duyệt?', 'Enable AI consent after approval?'))) void post('/ai/control/enable', { policy_id: policyId, approval_id: approved.id }, control); }}>{tr('Bật quyền AI', 'Enable AI consent')}</button></>}
      <button disabled={busy} onClick={() => { if (window.confirm(tr('Tắt quyền AI và vô hiệu yêu cầu cũ?', 'Disable AI consent and invalidate older requests?'))) void post('/ai/control/disable', {}, control); }}>{tr('Tắt quyền AI', 'Disable AI consent')}</button></>}
    {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
  </section>;
}
