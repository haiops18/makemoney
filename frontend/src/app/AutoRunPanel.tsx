import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

type Request = (path: string, init?: RequestInit) => Promise<unknown>;
type Tr = (vi: string, en: string) => string;

export const autoRunSchema = z.object({ id: z.string().uuid(), status: z.enum(['ACTIVE', 'COMPLETED', 'STOPPED']), stop_reason: z.string().nullable(), expires_at: z.string(), created_at: z.string(), ended_at: z.string().nullable() });
export type AutoRun = z.infer<typeof autoRunSchema>;
const plan = z.object({
  action: z.object({ policy_id: z.string(), action_type: z.string(), action_payload: z.record(z.string(), z.unknown()), resource_type: z.string(), resource_id: z.string(), scope: z.literal('ONCE') }),
  summary: z.object({ task_count: z.number(), ai_task_count: z.number(), max_cost_usd: z.string(), source_count: z.number(), models: z.array(z.string()) }),
});
const idOnly = z.object({ id: z.string().uuid() });
const submission = z.object({ approval_id: z.string().uuid() });
const workflowStatus = z.object({ status: z.string(), version: z.number() });

/** Latest auto-run of a workflow (null when never approved). Shared by the panel and task list. */
export function useAutoRun(request: Request, workflowId: string, enabled: boolean) {
  return useQuery({ queryKey: ['workflow-auto-run', workflowId], enabled: enabled && !!workflowId, refetchInterval: 3000,
    queryFn: async () => autoRunSchema.nullable().parse(await request(`/workflows/${workflowId}/auto-run`)) });
}

const KNOWN_REASONS: [string, string, string][] = [
  ['Add at least one research source', 'Bản nháp nghiên cứu chưa có nguồn nào. Thêm ít nhất 1 nguồn ở trang Nghiên cứu AI rồi thử lại.', 'The research draft has no sources. Add at least one on the AI research page, then retry.'],
  ['Add the AI stages', 'Workflow chưa có giai đoạn AI. Bấm "Thêm giai đoạn AI" ở trang Nghiên cứu AI trước.', 'The workflow has no AI stages yet. Add them on the AI research page first.'],
  ['Global AI consent is disabled', 'Quyền AI toàn cục đang tắt. Bật lại ở trang Cài đặt AI.', 'Global AI consent is off. Turn it on in AI settings.'],
  ['changed after the auto-run approval', 'Dữ liệu, nguồn hoặc cấu hình AI đã thay đổi sau khi duyệt. Hãy duyệt chạy tự động lại.', 'Data, sources or AI configuration changed after approval. Approve the auto-run again.'],
  ['cost limit is exhausted', 'Đã chạm trần chi phí của bản nghiên cứu.', 'The research cost limit was reached.'],
  ['Stopped by Owner', 'Anh/chị đã dừng chạy tự động.', 'Stopped by the Owner.'],
  ['expired', 'Phê duyệt chạy tự động đã hết hạn (12 giờ).', 'The auto-run approval expired (12 hours).'],
  ['Workflow failed', 'Một task bị lỗi nên workflow dừng. Xem lịch sử thực thi bên dưới.', 'A task failed, so the workflow stopped. See the execution history below.'],
  ['Workflow cancelled', 'Workflow đã bị hủy.', 'The workflow was cancelled.'],
];

export function explainReason(reason: string, tr: Tr): string {
  const known = KNOWN_REASONS.find(([needle]) => reason.includes(needle));
  return known ? tr(known[1], known[2]) : reason;
}

type Props = {
  request: Request; tr: Tr; locale: string; workflowId: string; status: string; aiPolicyId?: string; internalPolicyId?: string;
  pendingApproval?: { id: string; status: string }; hasAITasks: boolean; autoRun?: AutoRun | null; onChanged: () => Promise<void>;
};

const FINISHED = ['COMPLETED', 'FAILED', 'CANCELLED'];

/** One Owner approval for the whole workflow; the worker then runs each stage in dependency order. */
export default function AutoRunPanel({ request, tr, locale, workflowId, status, aiPolicyId, internalPolicyId, pendingApproval, hasAITasks, autoRun, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = autoRun?.status === 'ACTIVE';
  const post = (path: string, body: unknown = {}) => request(path, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(body) });
  const soon = () => new Date(Date.now() + 15 * 60000).toISOString();
  const planPath = () => `/workflows/${workflowId}/auto-run-action?ai_policy_id=${encodeURIComponent(aiPolicyId ?? '')}&internal_policy_id=${encodeURIComponent(internalPolicyId ?? '')}`;

  /** DRAFT/PENDING_APPROVAL → QUEUED with the existing workflow approval, recorded as the Owner's own decision. */
  async function startWorkflow(current: string) {
    let state = current;
    const approvalReason = { reason: tr('Owner duyệt chạy tự động toàn bộ workflow', 'Owner approved running the whole workflow') };
    if (state === 'PENDING_APPROVAL' && pendingApproval?.status !== 'PENDING' && pendingApproval?.status !== 'APPROVED') {
      state = workflowStatus.parse(await post(`/workflows/${workflowId}/reopen`)).status;
    }
    if (state === 'DRAFT') {
      const submitted = submission.parse(await post(`/workflows/${workflowId}/submit`, { policy_id: internalPolicyId, expires_at: soon() }));
      await post(`/approvals/${submitted.approval_id}/approve`, approvalReason);
    } else if (state === 'PENDING_APPROVAL' && pendingApproval?.status === 'PENDING') {
      await post(`/approvals/${pendingApproval.id}/approve`, approvalReason);
    }
    if (state === 'DRAFT' || state === 'PENDING_APPROVAL') await post(`/workflows/${workflowId}/start`);
  }

  async function approveAndRun() {
    if (!aiPolicyId || !internalPolicyId) return;
    setError(''); setBusy(true);
    try {
      const preview = plan.parse(await request(planPath())).summary;
      const message = tr(
        `Phê duyệt chạy tự động toàn bộ workflow?\n\n• ${preview.task_count} bước (${preview.ai_task_count} bước AI trả phí), chạy lần lượt theo thứ tự\n• Model: ${preview.models.join(', ')}\n• Nguồn: ${preview.source_count}\n• Trần chi phí cả bản nghiên cứu: ${preview.max_cost_usd} USD\n\nMỗi bước vẫn kiểm tra quyền AI và ngân sách. Hệ thống tự dừng nếu có lỗi hoặc dữ liệu thay đổi. Không tự chạy lại request trả phí.`,
        `Approve running the whole workflow automatically?\n\n• ${preview.task_count} steps (${preview.ai_task_count} paid AI steps), run in order\n• Models: ${preview.models.join(', ')}\n• Sources: ${preview.source_count}\n• Research cost limit: ${preview.max_cost_usd} USD\n\nEach step still checks AI consent and budget. It stops on any error or data change and never retries a paid request.`);
      if (!window.confirm(message)) return;
      await startWorkflow(status);
      // Re-derive after start so the approval binds the exact current plan.
      const current = plan.parse(await request(planPath())).action;
      const created = idOnly.parse(await post('/approvals', { policy_id: current.policy_id, action_type: current.action_type, action_payload: current.action_payload, resource_type: current.resource_type,
        resource_id: current.resource_id, scope: current.scope, expires_at: soon(), reason: tr('Phê duyệt chạy tự động toàn bộ workflow', 'Approve automatic run of the whole workflow') }));
      await post(`/approvals/${created.id}/approve`, { reason: tr('Owner duyệt chạy tự động toàn bộ workflow', 'Owner approved running the whole workflow') });
      autoRunSchema.parse(await post(`/workflows/${workflowId}/auto-run`, { ai_policy_id: aiPolicyId, internal_policy_id: internalPolicyId, approval_id: created.id }));
    } catch (caught) {
      setError(explainReason(caught instanceof Error ? caught.message : tr('Không thể bật chạy tự động.', 'Could not start the auto-run.'), tr));
    } finally {
      setBusy(false); await onChanged();
    }
  }

  async function stop() {
    if (!window.confirm(tr('Dừng chạy tự động? Bước đang chạy (nếu có) vẫn hoàn tất; các bước sau sẽ không tự chạy nữa.', 'Stop the auto-run? A step already running still finishes; later steps will not start.'))) return;
    setError(''); setBusy(true);
    try { autoRunSchema.parse(await post(`/workflows/${workflowId}/auto-run/stop`)); } catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không thể dừng.', 'Could not stop.')); } finally { setBusy(false); await onChanged(); }
  }

  const time = (value: string) => new Date(value).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' });
  const blocked = !aiPolicyId ? tr('Chưa có chính sách AI được bật.', 'No enabled AI policy.') : !internalPolicyId ? tr('Chưa có chính sách nội bộ được bật.', 'No enabled internal policy.')
    : !hasAITasks ? tr('Workflow chưa có giai đoạn AI.', 'The workflow has no AI stages.') : '';
  return <section className="panel auto-run" aria-labelledby="auto-run-title">
    <h3 id="auto-run-title">{tr('Chạy tự động', 'Automatic run')}</h3>
    <p className="muted">{tr('Duyệt một lần cho cả workflow. Các bước sẽ tự chạy lần lượt theo thứ tự phụ thuộc. Mỗi bước vẫn kiểm tra quyền AI và ngân sách, và tự dừng nếu có lỗi hoặc dữ liệu thay đổi.',
      'Approve once for the whole workflow; steps run by themselves in dependency order. Each step still checks AI consent and budget and stops on any error or data change.')}</p>
    <p data-testid="auto-run-status">{!autoRun ? tr('Trạng thái: chưa bật', 'Status: not started')
      : autoRun.status === 'ACTIVE' ? `${tr('Trạng thái: đang chạy tự động · hết hạn', 'Status: running automatically · expires')} ${time(autoRun.expires_at)}`
      : autoRun.status === 'COMPLETED' ? tr('Trạng thái: đã chạy xong toàn bộ', 'Status: completed')
      : `${tr('Trạng thái: đã dừng', 'Status: stopped')} · ${explainReason(autoRun.stop_reason ?? '', tr)}`}</p>
    {blocked && !active && !FINISHED.includes(status) && <p role="alert">{blocked}</p>}
    {busy && <p role="status">{tr('Đang xử lý…', 'Working…')}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="toolbar">
      {!active && !FINISHED.includes(status) && <button className="primary" disabled={busy || !!blocked} onClick={() => void approveAndRun()}>{tr('Phê duyệt & chạy tự động', 'Approve & run automatically')}</button>}
      {active && <button disabled={busy} onClick={() => void stop()}>{tr('Dừng chạy tự động', 'Stop auto-run')}</button>}
    </div>
  </section>;
}
