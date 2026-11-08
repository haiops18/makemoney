import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import AutoRunPanel, { useAutoRun } from './AutoRunPanel';
import ContentReview from './ContentReview';
import { AccesstradeImport, PostingSchedule, StandingAttestations } from './CampaignAutopilot';
import { linkSchema, type useCampaignApi, useTr } from './campaignApi';

type Api = ReturnType<typeof useCampaignApi>;
const TYPES = ['SOCIAL_POST', 'SHORT_CAPTION', 'VIDEO_SCRIPT', 'REVIEW_ARTICLE', 'COMPARISON', 'CTA_LANDING'] as const;
const batchSchema = z.object({ run_id: z.string().uuid(), workflow_id: z.string().uuid().nullable(), workflow_status: z.string().nullable(), content_types: z.array(z.string()),
  count_per_type: z.number(), max_cost_usd: z.string(), affiliate_link_id: z.string().uuid(), source_count: z.number(), item_count: z.number(), created_at: z.string() });
type Batch = z.infer<typeof batchSchema>;
const claimSchema = z.object({ classification: z.string(), statement: z.string(), source_ids: z.array(z.string()) });
const versionSchema = z.object({ version_no: z.number(), title: z.string(), body: z.string(), hashtags: z.array(z.string()), cta: z.string(), claims: z.array(claimSchema), author_kind: z.string(), created_at: z.string() });
const contentSchema = z.object({ id: z.string().uuid(), batch_run_id: z.string().uuid(), content_type: z.string(), status: z.string(), current_version: versionSchema, created_at: z.string() });
const policySchema = z.array(z.object({ id: z.string(), enabled: z.boolean(), rules_json: z.object({ allowed_action_types: z.array(z.string()) }) }));
const usageLine = z.object({ key: z.string(), invocations: z.number(), calculated_cost: z.string(), held_amount: z.string() });
const usageSchema = z.object({ max_cost_usd: z.string(), batch_limits_total: z.string(), invocations: z.number(), calculated_cost: z.string(), held_amount: z.string(), by_agent: z.array(usageLine) });

export default function CampaignContent({ api, campaignId, campaignStatus }: { api: Api; campaignId: string; campaignStatus: string }) {
  const { tr } = useTr();
  const cache = useQueryClient();
  const links = useQuery({ queryKey: ['campaigns', campaignId, 'links'], queryFn: async () => z.array(linkSchema).parse(await api.request(`/campaigns/${campaignId}/links`)) });
  const batches = useQuery({ queryKey: ['campaigns', campaignId, 'batches'], refetchInterval: 5000, queryFn: async () => z.array(batchSchema).parse(await api.request(`/campaigns/${campaignId}/content-batches`)) });
  const content = useQuery({ queryKey: ['campaigns', campaignId, 'content'], refetchInterval: 5000, queryFn: async () => z.array(contentSchema).parse(await api.request(`/campaigns/${campaignId}/content`)) });
  const usage = useQuery({ queryKey: ['campaigns', campaignId, 'usage'], queryFn: async () => usageSchema.parse(await api.request(`/campaigns/${campaignId}/usage`)) });
  const [form, setForm] = useState({ affiliate_link_id: '', types: ['SOCIAL_POST', 'SHORT_CAPTION'] as string[], count: '1', max_cost_usd: '0.5' });
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const [opened, setOpened] = useState('');
  const statusLabel: Record<string, string> = { DRAFT: tr('Nháp', 'Draft'), CHECK_FAILED: tr('Kiểm tra không đạt', 'Checks failed'), IN_REVIEW: tr('Chờ duyệt', 'In review'),
    APPROVED: tr('Đã duyệt', 'Approved'), REJECTED: tr('Đã từ chối', 'Rejected'), READY_TO_PUBLISH: tr('Sẵn sàng đăng', 'Ready to post'), PUBLISHED: tr('Đã đăng', 'Posted') };
  const activeLinks = links.data?.filter(item => item.status === 'ACTIVE') ?? [];
  const labels: Record<string, string> = { SOCIAL_POST: tr('Bài mạng xã hội', 'Social post'), SHORT_CAPTION: tr('Caption video ngắn', 'Short-video caption'), VIDEO_SCRIPT: tr('Kịch bản video', 'Video script'),
    REVIEW_ARTICLE: tr('Bài đánh giá', 'Review article'), COMPARISON: tr('Bài so sánh', 'Comparison'), CTA_LANDING: tr('CTA / landing', 'CTA / landing') };
  const total = form.types.length * Number(form.count);

  async function create(event: React.FormEvent) {
    event.preventDefault(); setMessage(null);
    try {
      await api.send('POST', `/campaigns/${campaignId}/content-batches`, { affiliate_link_id: form.affiliate_link_id, content_types: form.types, count_per_type: Number(form.count), max_cost_usd: form.max_cost_usd }, batchSchema);
      setMessage({ error: false, text: tr('Đã tạo lô nội dung. Bấm "Phê duyệt & chạy tự động" bên dưới để AI soạn.', 'Batch created. Use "Approve & run automatically" below to draft it.') });
    } catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không thể tạo lô.', 'Could not create the batch.') }); }
  }

  return <>
    <p className="muted">{tr('AI soạn bản nháp từ dữ liệu đã chụp lại của chiến dịch. AI không thấy link thật: nó chỉ viết chỗ giữ {{AFFILIATE_LINK}}. Mỗi lô chỉ chạy khi anh/chị duyệt, trong trần chi phí và ngân sách.',
      'AI drafts from a frozen snapshot of the campaign. It never sees the real link, only the {{AFFILIATE_LINK}} placeholder. A batch runs only after your approval, within its cost limit and budget.')}</p>
    {usage.data && <p data-testid="campaign-usage">{tr('Chi phí AI (ước tính)', 'AI cost (estimate)')}: {usage.data.calculated_cost} USD · {tr('đang giữ', 'held')} {usage.data.held_amount} USD · {tr('đã phân bổ cho các lô', 'allocated to batches')} {usage.data.batch_limits_total}/{usage.data.max_cost_usd} USD</p>}
    <AccesstradeImport api={api} campaignId={campaignId} editable={campaignStatus !== 'ARCHIVED'}/>
    <StandingAttestations api={api} campaignId={campaignId} editable={campaignStatus !== 'ARCHIVED'}/>
    <PostingSchedule api={api} campaignId={campaignId} active={campaignStatus === 'ACTIVE'}/>
    {campaignStatus !== 'ACTIVE' ? <p className="muted">{tr('Kích hoạt chiến dịch ở tab Tổng quan để tạo nội dung.', 'Activate the campaign on the Overview tab to create content.')}</p>
      : <form className="panel" onSubmit={event => void create(event)}><h3>{tr('Tạo lô nội dung', 'New content batch')}</h3>
        <label className="field">{tr('Link affiliate', 'Affiliate link')}<select value={form.affiliate_link_id} onChange={event => setForm({ ...form, affiliate_link_id: event.target.value })} required>
          <option value="">{tr('— Chọn —', '— Choose —')}</option>{activeLinks.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        {links.data && !activeLinks.length && <p className="muted">{tr('Chưa có link đang dùng. Thêm link ở tab Link affiliate.', 'No active link. Add one on the Affiliate links tab.')}</p>}
        <fieldset className="field"><legend>{tr('Loại nội dung', 'Content types')}</legend>{TYPES.map(type => <label key={type} className="login-remember">
          <input type="checkbox" checked={form.types.includes(type)} onChange={event => setForm({ ...form, types: event.target.checked ? [...form.types, type] : form.types.filter(item => item !== type) })}/>{labels[type]}</label>)}</fieldset>
        <label className="field">{tr('Số bài mỗi loại', 'Items per type')}<select value={form.count} onChange={event => setForm({ ...form, count: event.target.value })}>{['1', '2', '3'].map(value => <option key={value}>{value}</option>)}</select></label>
        <label className="field">{tr('Trần chi phí của lô (USD)', 'Batch cost limit (USD)')}<input type="number" min="0.000001" max="45" step="0.000001" value={form.max_cost_usd} onChange={event => setForm({ ...form, max_cost_usd: event.target.value })} required/></label>
        {total > 10 && <p className="form-error" role="alert">{tr('Một lô tối đa 10 bài.', 'A batch has at most 10 items.')}</p>}
        <button className="primary" disabled={api.busy || !form.types.length || total > 10}>{tr(`Tạo lô ${total} bài`, `Create batch of ${total}`)}</button>
      </form>}
    {message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
    <h3>{tr('Các lô nội dung', 'Content batches')}</h3>
    {batches.isLoading && <p role="status">{tr('Đang tải…', 'Loading…')}</p>}
    {batches.error && <p role="alert">{tr('Không thể tải lô.', 'Unable to load batches.')}</p>}
    {batches.data?.length === 0 && <p className="empty">{tr('Chưa có lô nội dung.', 'No batches yet.')}</p>}
    {batches.data?.map(batch => <BatchCard key={batch.run_id} api={api} batch={batch} labels={labels} onChanged={async () => { await cache.invalidateQueries({ queryKey: ['campaigns', campaignId] }); }}/>)}
    <h3>{tr('Bản nháp nội dung', 'Content drafts')}</h3>
    {content.error && <p role="alert">{tr('Không thể tải nội dung.', 'Unable to load content.')}</p>}
    {content.data?.length === 0 && <p className="empty">{tr('Chưa có bản nháp.', 'No drafts yet.')}</p>}
    <div className="table">{content.data?.map(item => <details className="content-item" key={item.id} open={opened === item.id} onToggle={event => { const open = (event.currentTarget as HTMLDetailsElement).open; if (open) setOpened(item.id); else if (opened === item.id) setOpened(''); }}>
      <summary><b>{item.current_version.title}</b> · {labels[item.content_type] ?? item.content_type} · <span className="badge">{statusLabel[item.status] ?? item.status}</span></summary>
      {opened === item.id && <ContentReview api={api} campaignId={campaignId} contentId={item.id}/>}
    </details>)}</div>
  </>;
}

function BatchCard({ api, batch, labels, onChanged }: { api: Api; batch: Batch; labels: Record<string, string>; onChanged: () => Promise<void> }) {
  const { tr, locale } = useTr();
  const policies = useQuery({ queryKey: ['campaigns', 'policies'], queryFn: async () => policySchema.parse(await api.request('/policies')) });
  const autoRun = useAutoRun(api.request, batch.workflow_id ?? '', !!batch.workflow_id);
  const ai = policies.data?.find(item => item.enabled && item.rules_json.allowed_action_types.includes('AI_INFERENCE'));
  const internal = policies.data?.find(item => item.enabled && item.rules_json.allowed_action_types.includes('INTERNAL_WORKFLOW'));
  return <article className="panel"><p><b>{batch.content_types.map(type => labels[type] ?? type).join(', ')}</b> × {batch.count_per_type} · {batch.max_cost_usd} USD · {batch.source_count} {tr('nguồn', 'sources')} · {batch.item_count} {tr('bài đã soạn', 'drafted')}</p>
    <p className="muted">{new Date(batch.created_at).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })} · Workflow: {batch.workflow_status ?? '—'}</p>
    {batch.workflow_id && batch.workflow_status && <AutoRunPanel request={api.request} tr={tr} locale={locale} workflowId={batch.workflow_id} status={batch.workflow_status} aiPolicyId={ai?.id} internalPolicyId={internal?.id}
      hasAITasks autoRun={autoRun.data} onChanged={async () => { await autoRun.refetch(); await onChanged(); }}/>}
  </article>;
}
