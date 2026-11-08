import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { z } from 'zod';
import AutoRunPanel, { useAutoRun } from './AutoRunPanel';
import { useCampaignApi, useTr, type Tr } from './campaignApi';

type Api = ReturnType<typeof useCampaignApi>;
const summarySchema = z.object({ run_id: z.string().uuid(), topic: z.string(), target_market: z.string().nullable(), max_cost_usd: z.string(), workflow_id: z.string().uuid().nullable(),
  workflow_status: z.string().nullable(), source_count: z.number(), candidate_count: z.number(), created_at: z.string() });
const ideaSchema = z.object({ summary: z.string(), how_it_works: z.array(z.string()), income_low_vnd: z.number(), income_base_vnd: z.number(), income_high_vnd: z.number(),
  startup_cost_vnd: z.number(), monthly_cost_vnd: z.number(), weeks_to_first_income: z.number(), hours_per_week: z.number(), success_likelihood: z.number(),
  risk_level: z.string(), risks: z.array(z.string()), required_integrations: z.array(z.string()), assumptions: z.array(z.string()) });
const candidateSchema = z.object({ id: z.string().uuid(), title: z.string(), business_model: z.string(), status: z.enum(['PROPOSED', 'APPROVED', 'REJECTED']), rank_value: z.number(),
  data: ideaSchema, decided_by: z.string().nullable(), decision_note: z.string().nullable(), opportunity_id: z.string().uuid().nullable() });
const detailSchema = summarySchema.extend({ queries: z.array(z.string()), ranking_summary: z.string().nullable(),
  sources: z.array(z.object({ id: z.string().uuid(), source_name: z.string(), source_url: z.string().nullable(), excerpt: z.string(), verification_status: z.string() })),
  candidates: z.array(candidateSchema) });
const policySchema = z.array(z.object({ id: z.string(), enabled: z.boolean(), rules_json: z.object({ allowed_action_types: z.array(z.string()) }) }));
const integrationSchema = z.array(z.object({ kind: z.string(), enabled: z.boolean(), has_secret: z.boolean() }));
type Candidate = z.infer<typeof candidateSchema>;

const vnd = (value: number, locale: string) => `${value.toLocaleString(locale)}đ`;

export default function Discovery({ token }: { token: string }) {
  const { tr } = useTr();
  const api = useCampaignApi(token);
  const list = useQuery({ queryKey: ['campaigns', 'discovery'], enabled: !!token, queryFn: async () => z.array(summarySchema).parse(await api.request('/discovery')) });
  const integrations = useQuery({ queryKey: ['campaigns', 'integrations'], enabled: !!token, queryFn: async () => integrationSchema.parse(await api.request('/integrations')) });
  const [form, setForm] = useState({ topic: '', target_market: 'Việt Nam', budget_note: '', max_cost_usd: '2', query_count: '4', results_per_query: '4' });
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const [opened, setOpened] = useState('');
  const hasSearch = integrations.data?.some(item => item.kind.startsWith('SEARCH_') && item.enabled && item.has_secret);
  const queries = Number(form.query_count);

  async function start(event: React.FormEvent) {
    event.preventDefault(); setMessage(null);
    if (!window.confirm(tr(`App sẽ dùng ${queries} lượt tìm kiếm web có tính phí của nguồn tìm kiếm anh/chị đã kết nối. Tiếp tục?`, `The app will use ${queries} paid web search queries. Continue?`))) return;
    try {
      const created = await api.send('POST', '/discovery', { topic: form.topic, target_market: form.target_market, budget_note: form.budget_note || null, max_cost_usd: form.max_cost_usd,
        query_count: queries, results_per_query: Number(form.results_per_query) }, detailSchema);
      setOpened(created.run_id);
      setMessage({ error: false, text: tr(`Đã tìm được ${created.source_count} nguồn. Bấm "Phê duyệt & chạy tự động" để AI phân tích và xếp hạng.`, `Found ${created.source_count} sources. Use "Approve & run automatically" to analyse and rank.`) });
    } catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không thể tìm.', 'Search failed.') }); }
  }

  return <section>
    <div className="page-head"><div><p className="eyebrow">{tr('Bước 1 — Tìm cơ hội', 'Step 1 — Discover')}</p><h1>{tr('Tìm cách kiếm tiền', 'Find ways to earn')}</h1>
      <p>{tr('Nhập lĩnh vực anh/chị quan tâm. App tự tìm trên Internet, AI phân tích qua 7 bước rồi xếp hạng các hướng theo thu nhập ước tính và khả năng thành công. Anh/chị duyệt hướng nào thì app tạo cơ hội đã chấm điểm cho hướng đó.',
        'Enter a field. The app searches the web, the AI analyses it in 7 stages and ranks ideas by estimated income and likelihood. Approving an idea creates a scored opportunity.')}</p></div></div>
    {integrations.data && !hasSearch && <p className="form-error" role="alert">{tr('Chưa có nguồn tìm kiếm. ', 'No search source yet. ')}<Link to="/integrations">{tr('Kết nối Tavily hoặc Brave Search', 'Connect Tavily or Brave Search')}</Link>.</p>}
    <form className="panel" onSubmit={event => void start(event)}><h3>{tr('Tìm cơ hội mới', 'New discovery')}</h3>
      <label className="field">{tr('Lĩnh vực / chủ đề', 'Field / topic')}<input value={form.topic} minLength={2} maxLength={150} required placeholder={tr('Ví dụ: thời trang nữ, đồ gia dụng, khóa học online', 'e.g. women’s fashion')}
        onChange={event => setForm({ ...form, topic: event.target.value })}/></label>
      <label className="field">{tr('Thị trường', 'Market')}<input value={form.target_market} maxLength={200} required onChange={event => setForm({ ...form, target_market: event.target.value })}/></label>
      <label className="field">{tr('Điều kiện của anh/chị (tuỳ chọn)', 'Your constraints (optional)')}<input value={form.budget_note} maxLength={500} placeholder={tr('Ví dụ: vốn dưới 2 triệu, 1 giờ mỗi ngày', 'e.g. under 2M VND, 1 hour a day')}
        onChange={event => setForm({ ...form, budget_note: event.target.value })}/></label>
      <label className="field">{tr('Số lượt tìm kiếm', 'Search queries')}<select value={form.query_count} onChange={event => setForm({ ...form, query_count: event.target.value })}>{['2', '3', '4', '5', '6'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="field">{tr('Kết quả mỗi lượt', 'Results per query')}<select value={form.results_per_query} onChange={event => setForm({ ...form, results_per_query: event.target.value })}>{['2', '3', '4', '5'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="field">{tr('Trần chi phí AI (USD)', 'AI cost limit (USD)')}<input type="number" min="0.01" max="10" step="0.01" value={form.max_cost_usd} required onChange={event => setForm({ ...form, max_cost_usd: event.target.value })}/></label>
      <button className="primary" disabled={api.busy || !hasSearch || form.topic.trim().length < 2}>{api.busy ? tr('Đang tìm…', 'Searching…') : tr('Tìm cơ hội', 'Discover')}</button>
    </form>
    {message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
    <h3>{tr('Các lượt tìm', 'Discoveries')}</h3>
    {list.isLoading && <p role="status">{tr('Đang tải…', 'Loading…')}</p>}
    {list.error && <p role="alert">{tr('Không thể tải danh sách.', 'Unable to load discoveries.')}</p>}
    {list.data?.length === 0 && <p className="empty">{tr('Chưa có lượt tìm nào.', 'No discoveries yet.')}</p>}
    <div className="table">{list.data?.map(item => <details className="content-item" key={item.run_id} open={opened === item.run_id}
      onToggle={event => { const open = (event.currentTarget as HTMLDetailsElement).open; if (open) setOpened(item.run_id); else if (opened === item.run_id) setOpened(''); }}>
      <summary><b>{item.topic}</b> · {item.source_count} {tr('nguồn', 'sources')} · {item.candidate_count} {tr('hướng', 'ideas')} · <span className="badge">{item.workflow_status ?? '—'}</span></summary>
      {opened === item.run_id && <DiscoveryDetail api={api} runId={item.run_id}/>}
    </details>)}</div>
  </section>;
}

function DiscoveryDetail({ api, runId }: { api: Api; runId: string }) {
  const { tr, locale } = useTr();
  const cache = useQueryClient();
  const detail = useQuery({ queryKey: ['campaigns', 'discovery', runId], refetchInterval: 5000, queryFn: async () => detailSchema.parse(await api.request(`/discovery/${runId}`)) });
  const policies = useQuery({ queryKey: ['campaigns', 'policies'], queryFn: async () => policySchema.parse(await api.request('/policies')) });
  const workflowId = detail.data?.workflow_id ?? '';
  const autoRun = useAutoRun(api.request, workflowId, !!workflowId);
  const ai = policies.data?.find(item => item.enabled && item.rules_json.allowed_action_types.includes('AI_INFERENCE'));
  const internal = policies.data?.find(item => item.enabled && item.rules_json.allowed_action_types.includes('INTERNAL_WORKFLOW'));
  if (detail.isLoading) return <p role="status">{tr('Đang tải…', 'Loading…')}</p>;
  if (detail.error || !detail.data) return <p role="alert">{tr('Không thể tải lượt tìm.', 'Unable to load this discovery.')}</p>;
  const data = detail.data;
  return <div className="panel">
    <p className="muted">{tr('Trần chi phí AI', 'AI cost limit')}: {data.max_cost_usd} USD · {tr('Truy vấn', 'Queries')}: {data.queries.join(' · ')}</p>
    {data.workflow_id && data.workflow_status && <AutoRunPanel request={api.request} tr={tr} locale={locale} workflowId={data.workflow_id} status={data.workflow_status}
      aiPolicyId={ai?.id} internalPolicyId={internal?.id} hasAITasks autoRun={autoRun.data} onChanged={async () => { await autoRun.refetch(); await cache.invalidateQueries({ queryKey: ['campaigns', 'discovery'] }); }}/>}
    {data.ranking_summary && <p><b>{tr('Nhận xét của AI', 'AI summary')}:</b> {data.ranking_summary}</p>}
    {data.candidates.length === 0 && data.workflow_status !== 'COMPLETED' && <p className="muted">{tr('Bảng xếp hạng sẽ hiện ở đây sau khi AI chạy xong 8 bước.', 'The ranking appears here once the AI finishes all 8 stages.')}</p>}
    {data.candidates.length > 0 && <p className="muted">{tr('Mọi con số là ước tính của AI từ kết quả tìm kiếm chưa xác minh, không phải cam kết thu nhập.', 'All figures are AI estimates from unverified search results, not income promises.')}</p>}
    <ol className="table">{data.candidates.map(item => <CandidateCard key={item.id} api={api} runId={runId} item={item}/>)}</ol>
    <details><summary>{tr(`Nguồn đã tìm (${data.sources.length}, chưa xác minh)`, `Sources found (${data.sources.length}, unverified)`)}</summary>
      <ul>{data.sources.map(source => <li key={source.id}><b>{source.source_name}</b> — {source.excerpt}{source.source_url && <> · <span className="muted">{source.source_url}</span></>}</li>)}</ul></details>
  </div>;
}

function risk(tr: Tr, level: string) {
  return ({ LOW: tr('Thấp', 'Low'), MEDIUM: tr('Trung bình', 'Medium'), HIGH: tr('Cao', 'High'), SEVERE: tr('Nghiêm trọng', 'Severe') } as Record<string, string>)[level] ?? level;
}

function CandidateCard({ api, runId, item }: { api: Api; runId: string; item: Candidate }) {
  const { tr, locale } = useTr();
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const idea = item.data;
  async function decide(action: 'approve' | 'reject') {
    setError('');
    try { await api.send('POST', `/discovery/${runId}/candidates/${item.id}/${action}`, { note }, candidateSchema); }
    catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không thể lưu quyết định.', 'Unable to save the decision.')); }
  }
  return <li className="panel" data-testid="candidate">
    <h4>{item.title} <span className="badge">{item.business_model}</span></h4>
    <p>{idea.summary}</p>
    <div className="status-grid">
      <div><b>{tr('Thu nhập/tháng (ước tính)', 'Income/month (estimate)')}</b><span>{vnd(idea.income_low_vnd, locale)} – {vnd(idea.income_high_vnd, locale)}</span><span className="muted">{tr('cơ sở', 'base')} {vnd(idea.income_base_vnd, locale)}</span></div>
      <div><b>{tr('Khả năng đạt mức cơ sở', 'Likelihood of base')}</b><span>{idea.success_likelihood}%</span></div>
      <div><b>{tr('Vốn / chi phí tháng', 'Startup / monthly cost')}</b><span>{vnd(idea.startup_cost_vnd, locale)} / {vnd(idea.monthly_cost_vnd, locale)}</span></div>
      <div><b>{tr('Thời gian & công sức', 'Time & effort')}</b><span>{tr(`~${idea.weeks_to_first_income} tuần · ${idea.hours_per_week} giờ/tuần`, `~${idea.weeks_to_first_income} weeks · ${idea.hours_per_week} h/week`)}</span></div>
      <div><b>{tr('Rủi ro', 'Risk')}</b><span>{risk(tr, idea.risk_level)}</span></div>
    </div>
    <p><b>{tr('Cách làm', 'How it works')}:</b> {idea.how_it_works.join(' → ')}</p>
    <p className="muted"><b>{tr('Rủi ro', 'Risks')}:</b> {idea.risks.join('; ')} · <b>{tr('Giả định', 'Assumptions')}:</b> {idea.assumptions.join('; ')}</p>
    {item.status === 'PROPOSED' ? <>
      <label className="field">{tr('Ghi chú quyết định', 'Decision note')}<input value={note} maxLength={1000} onChange={event => setNote(event.target.value)}/></label>
      <div className="toolbar"><button className="primary" disabled={api.busy || !note.trim()} onClick={() => void decide('approve')}>{tr('Duyệt hướng này', 'Approve this idea')}</button>
        <button disabled={api.busy || !note.trim()} onClick={() => void decide('reject')}>{tr('Bỏ qua', 'Reject')}</button></div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </> : <p role="status"><span className="badge">{item.status === 'APPROVED' ? tr('Đã duyệt', 'Approved') : tr('Đã bỏ qua', 'Rejected')}</span> {item.decision_note}
      {item.opportunity_id && <> · <Link to="/campaigns">{tr('Tạo chiến dịch từ cơ hội này', 'Create a campaign from it')}</Link></>}</p>}
  </li>;
}
