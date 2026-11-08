import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { z } from 'zod';
import { useCampaignApi, useTr } from './campaignApi';

const proposalSchema = z.object({ content_id: z.string().uuid(), campaign_id: z.string().uuid(), campaign_name: z.string(), content_type: z.string(), title: z.string(), body: z.string(),
  hashtags: z.array(z.string()), cta: z.string(), link_label: z.string().nullable(), ready: z.boolean(), open_checks: z.array(z.string()), created_at: z.string() });
type Proposal = z.infer<typeof proposalSchema>;
const decided = z.object({ id: z.string().uuid(), status: z.string() });

export default function Proposals({ token }: { token: string }) {
  const { tr } = useTr();
  const api = useCampaignApi(token);
  const list = useQuery({ queryKey: ['campaigns', 'proposals'], enabled: !!token, refetchInterval: 10000, queryFn: async () => z.array(proposalSchema).parse(await api.request('/proposals')) });
  const ready = list.data?.filter(item => item.ready) ?? [];
  const waiting = list.data?.filter(item => !item.ready) ?? [];
  return <section>
    <div className="page-head"><div><p className="eyebrow">{tr('Bước 3 — Duyệt', 'Step 3 — Review')}</p><h1>{tr('Đề xuất chờ duyệt', 'Proposals')}</h1>
      <p>{tr('Các bài AI soạn đã qua hết kiểm tra tự động. Anh/chị đọc lại, duyệt kèm ghi chú; bài đã duyệt sẽ được đăng theo lịch nếu anh/chị bật lịch đăng của chiến dịch.',
        'AI drafts that passed every automatic check. Read, approve with a note; approved items post on schedule if the campaign schedule is on.')}</p></div></div>
    {list.isLoading && <p role="status">{tr('Đang tải…', 'Loading…')}</p>}
    {list.error && <p role="alert">{tr('Không thể tải đề xuất.', 'Unable to load proposals.')}</p>}
    {list.data?.length === 0 && <p className="empty">{tr('Chưa có đề xuất nào.', 'No proposals yet.')}</p>}
    {ready.length > 0 && <h3>{tr(`Sẵn sàng duyệt (${ready.length})`, `Ready (${ready.length})`)}</h3>}
    <div className="table">{ready.map(item => <ProposalCard key={item.content_id} api={api} item={item}/>)}</div>
    {waiting.length > 0 && <><h3>{tr(`Cần anh/chị xác nhận thêm (${waiting.length})`, `Needs your confirmation (${waiting.length})`)}</h3>
      <p className="muted">{tr('Mẹo: xác nhận chung quyền hình ảnh và quảng cáo/thuế ở tab Nội dung của chiến dịch để các bài sau tự qua.', 'Tip: confirm media rights and ads/tax once on the campaign Content tab.')}</p>
      <div className="table">{waiting.map(item => <ProposalCard key={item.content_id} api={api} item={item}/>)}</div></>}
  </section>;
}

function ProposalCard({ api, item }: { api: ReturnType<typeof useCampaignApi>; item: Proposal }) {
  const { tr } = useTr();
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const base = `/campaigns/${item.campaign_id}/content/${item.content_id}`;
  async function decide(action: 'approve' | 'reject') {
    setError('');
    try { await api.send('POST', `${base}/${action}`, { note }, decided); }
    catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không lưu được.', 'Unable to save.')); }
  }
  return <article className="panel" data-testid="proposal">
    <p className="muted">{item.campaign_name} · {item.content_type}{item.link_label ? ` · ${tr('link', 'link')}: ${item.link_label}` : ''}</p>
    <h4>{item.title}</h4>
    <p style={{ whiteSpace: 'pre-wrap' }}>{item.body}</p>
    <p><b>{item.cta}</b> {item.hashtags.map(tag => `#${tag}`).join(' ')}</p>
    {!item.ready && <p className="form-error">{tr('Chưa qua', 'Still open')}: {item.open_checks.join(', ')} · <Link to="/campaigns">{tr('Mở chiến dịch để xử lý', 'Open the campaign')}</Link></p>}
    <label className="field">{tr('Ghi chú quyết định', 'Decision note')}<input value={note} maxLength={1000} onChange={event => setNote(event.target.value)}/></label>
    <div className="toolbar"><button className="primary" disabled={api.busy || !item.ready || !note.trim()} onClick={() => void decide('approve')}>{tr('Duyệt', 'Approve')}</button>
      <button disabled={api.busy || !note.trim()} onClick={() => void decide('reject')}>{tr('Từ chối', 'Reject')}</button></div>
    {error && <p className="form-error" role="alert">{error}</p>}
  </article>;
}
