import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { z } from 'zod';

const finding = z.object({ classification: z.string(), statement: z.string(), source_ids: z.array(z.string()), assumptions: z.array(z.string()) });
const stage = z.object({
  task_id: z.string().uuid(), name: z.string(), task_type: z.string(), assigned_role: z.string(), task_status: z.string(),
  invocation_status: z.string().nullable(), model_id: z.string().nullable(), error_code: z.string().nullable(),
  estimated_cost: z.string().nullable(), calculated_cost: z.string().nullable(), confirmed_cost: z.string().nullable(),
  output: z.object({ summary: z.string(), findings: z.array(finding) }).nullable(),
});
const results = z.object({ workflow_id: z.string().uuid().nullable(), workflow_status: z.string().nullable(), opportunity_id: z.string().uuid().nullable(), stages: z.array(stage) });
const pipeline = z.object({ workflow_id: z.string().uuid(), tasks: z.array(z.object({ id: z.string().uuid() })) });
const promoted = z.object({ opportunity_id: z.string().uuid(), evidence_count: z.number() });
const promoteForm = z.object({ title: z.string().trim().min(1).max(200), business_model: z.string().trim().min(1).max(100) });

export default function AIResearchStages({ token, runId, workflowStatus }: { token: string; runId: string; workflowStatus: string }) {
  const { i18n } = useTranslation(); const vi = i18n.language.startsWith('vi'); const tr = (a: string, b: string) => vi ? a : b;
  const cache = useQueryClient(); const retry = useRef<{ signature: string; key: string } | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [success, setSuccess] = useState('');
  const [title, setTitle] = useState(''); const [model, setModel] = useState('');
  const base = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/research/${runId}`;
  const query = useQuery({ queryKey: ['ai-research-results', runId], queryFn: async () => {
    const response = await fetch(`${base}/results`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return results.parse(await response.json());
  } });
  async function post<T>(path: string, body: Record<string, unknown>, schema: z.ZodType<T>, done: string) {
    setBusy(true); setError(''); setSuccess('');
    try {
      const serialized = JSON.stringify(body); const signature = `${path}:${serialized}`;
      if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      const response = await fetch(`${base}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': retry.current.key }, body: serialized });
      if (!response.ok) { const detail = await response.json().catch(() => null) as { detail?: unknown } | null; throw new Error(typeof detail?.detail === 'string' ? detail.detail : `API ${response.status}`); }
      schema.parse(await response.json()); retry.current = null;
      await Promise.all([cache.invalidateQueries({ queryKey: ['ai-research-results'] }), cache.invalidateQueries({ queryKey: ['ai-research'] })]);
      setSuccess(done);
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể lưu.', 'Unable to save.')); } finally { setBusy(false); }
  }
  const data = query.data;
  const report = data?.stages.find(item => item.task_type === 'AI_RESEARCH_REPORT' && item.output);
  return <section aria-labelledby={`stages-${runId}`}><h3 id={`stages-${runId}`}>{tr('Các giai đoạn AI', 'AI stages')}</h3>
    <p>{tr('Kết quả AI là phân tích chưa xác minh, không phải dữ kiện thị trường. Chi phí theo token là ước tính cho đến khi Owner đối soát.', 'AI output is unverified analysis, not market fact. Token-based cost is an estimate until the Owner reconciles it.')}</p>
    {query.isLoading && <p>{tr('Đang tải kết quả…', 'Loading results…')}</p>}{query.error && <p role="alert">{tr('Không thể tải kết quả.', 'Unable to load results.')}</p>}
    {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
    {data && data.stages.length === 0 && (workflowStatus === 'DRAFT'
      ? <div><p>{tr('Thêm 7 giai đoạn: kế hoạch, thị trường, đối thủ, cơ hội, tài chính, rủi ro, báo cáo. Cần hồ sơ AI và giá model cho từng agent. Việc này không chạy AI.', 'Adds 7 stages: plan, market, competitors, opportunity, finance, risk, report. Each agent needs an AI profile and model price. Nothing runs.')}</p>
        <button type="button" disabled={busy} onClick={() => void post('/pipeline', { confirm_no_execution: true }, pipeline, tr('Đã thêm các giai đoạn AI vào workflow bản nháp.', 'AI stages added to the draft workflow.'))}>{tr('Thêm giai đoạn AI', 'Add AI stages')}</button></div>
      : <p>{tr('Workflow không có giai đoạn AI.', 'This workflow has no AI stages.')}</p>)}
    {data?.stages.map(item => <article className="panel" key={item.task_id}><b>{item.name} · {item.task_status}</b>
      <p>{item.assigned_role} · {item.model_id ?? tr('Chưa chạy', 'Not run')} · {item.invocation_status ?? '—'}{item.error_code ? ` · ${item.error_code}` : ''}</p>
      {item.estimated_cost && <p>{tr('Ước tính', 'Estimate')} {item.estimated_cost} · {tr('Theo token', 'Token-based')} {item.calculated_cost ?? '—'} · {tr('Đã xác nhận', 'Confirmed')} {item.confirmed_cost ?? tr('chưa đối soát', 'not reconciled')} USD</p>}
      {item.output && <><p>{item.output.summary}</p><ul>{item.output.findings.map((row, index) => <li key={index}><b>{row.classification}</b> {row.statement}{row.assumptions.length ? ` (${tr('giả định', 'assumptions')}: ${row.assumptions.join('; ')})` : ''}{row.source_ids.length ? ` [${row.source_ids.length} ${tr('nguồn', 'sources')}]` : ''}</li>)}</ul></>}
    </article>)}
    {data && data.stages.length > 0 && <p><Link to="/workflows">{tr('Phê duyệt và chạy từng giai đoạn trong Workflow', 'Approve and run each stage in Workflows')}</Link> · <Link to="/ai-usage">{tr('Xem chi phí AI', 'View AI usage')}</Link></p>}
    {data?.opportunity_id && <p role="status">{tr('Đã tạo cơ hội từ nghiên cứu này.', 'An opportunity was created from this research.')} <Link to="/opportunities">{tr('Mở cơ hội', 'Open opportunity')}</Link></p>}
    {data && !data.opportunity_id && data.workflow_status === 'COMPLETED' && report && <form onSubmit={event => { event.preventDefault(); const parsed = promoteForm.safeParse({ title, business_model: model }); if (!parsed.success) { setError(tr('Nhập tiêu đề và mô hình kinh doanh.', 'Enter a title and business model.')); return; } void post('/promote', parsed.data, promoted, tr('Đã tạo cơ hội bản nháp. Hãy đánh giá trong Cơ hội.', 'Draft opportunity created. Evaluate it in Opportunities.')); }}>
      <h4>{tr('Tạo cơ hội từ báo cáo', 'Create opportunity from report')}</h4><p>{tr('Chỉ nguồn Owner nhập (không bị từ chối) trở thành bằng chứng. Chấm điểm vẫn do Owner thực hiện.', 'Only non-rejected Owner sources become evidence. Scoring remains an Owner step.')}</p>
      <label className="field">{tr('Tiêu đề cơ hội', 'Opportunity title')}<input value={title} onChange={event => setTitle(event.target.value)} maxLength={200} required/></label>
      <label className="field">{tr('Mô hình kinh doanh', 'Business model')}<select value={model} onChange={event => setModel(event.target.value)} required><option value="">—</option>{['MICRO_SAAS', 'DIGITAL_PRODUCTS', 'AFFILIATE_MARKETING', 'CONTENT_MARKETING', 'AI_SERVICES'].map(value => <option key={value}>{value}</option>)}</select></label>
      <button disabled={busy}>{tr('Tạo cơ hội', 'Create opportunity')}</button></form>}
  </section>;
}
