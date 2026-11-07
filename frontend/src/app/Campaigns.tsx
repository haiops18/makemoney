import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import CampaignDetail from './CampaignDetail';
import { campaignSchema, useCampaignApi, useTr } from './campaignApi';

const opportunity = z.object({ id: z.string().uuid(), title: z.string(), business_model: z.string(), score: z.number().nullable() });
const draft = z.object({
  opportunity_id: z.string().uuid(), name: z.string().trim().min(1).max(200), niche: z.string().trim().max(200).nullable(), target_audience: z.string().trim().max(500).nullable(),
  goal: z.string().trim().max(2000).nullable(), max_cost_usd: z.string().regex(/^\d{1,2}(?:\.\d{1,6})?$/).refine(value => Number(value) > 0 && Number(value) <= 45),
});

/** Step 7A: campaigns built from an evaluated opportunity. Level B — the app never posts or pays. */
export default function Campaigns({ token }: { token: string }) {
  const { tr, locale } = useTr();
  const api = useCampaignApi(token);
  const [selected, setSelected] = useState('');
  const [form, setForm] = useState({ opportunity_id: '', name: '', niche: '', target_audience: '', goal: '', max_cost_usd: '2' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const campaigns = useQuery({ queryKey: ['campaigns', 'list'], enabled: !!token, queryFn: async () => z.array(campaignSchema).parse(await api.request('/campaigns?limit=100')) });
  const evaluated = useQuery({ queryKey: ['campaigns', 'opportunities'], enabled: !!token,
    queryFn: async () => z.object({ items: z.array(opportunity) }).parse(await api.request('/opportunities?status_filter=EVALUATED&sort_by=score&limit=100')).items });
  const set = (field: keyof typeof form) => (event: { target: { value: string } }) => setForm({ ...form, [field]: event.target.value });

  async function create(event: React.FormEvent) {
    event.preventDefault(); setError(''); setSuccess('');
    const parsed = draft.safeParse({ ...form, niche: form.niche || null, target_audience: form.target_audience || null, goal: form.goal || null });
    if (!parsed.success) { setError(tr('Chọn cơ hội, nhập tên và chi phí tối đa từ 0 đến 45 USD.', 'Choose an opportunity, enter a name and a maximum cost up to 45 USD.')); return; }
    try {
      const created = await api.send('POST', '/campaigns', parsed.data, campaignSchema);
      setSelected(created.id); setForm({ ...form, name: '', niche: '', target_audience: '', goal: '' });
      setSuccess(tr('Đã tạo chiến dịch.', 'Campaign created.'));
    } catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không thể tạo chiến dịch.', 'Could not create the campaign.')); }
  }

  if (!token) return <section><h1>{tr('Chiến dịch', 'Campaigns')}</h1><p>{tr('Vui lòng đăng nhập Owner.', 'Sign in as Owner.')}</p></section>;
  return <section>
    <div className="page-head"><div><p className="eyebrow">{tr('STEP 7A · LEVEL B', 'STEP 7A · LEVEL B')}</p><h1>{tr('Chiến dịch', 'Campaigns')}</h1>
      <p>{tr('Biến một cơ hội đã đánh giá thành chiến dịch affiliate. App chỉ lưu và chuẩn bị; anh/chị tự đăng bài, app không tự đăng, không mở link và không thanh toán.', 'Turn an evaluated opportunity into an affiliate campaign. The app only stores and prepares; you post yourself. It never posts, opens links or pays.')}</p></div></div>
    <form className="panel" onSubmit={event => void create(event)} aria-labelledby="campaign-create-title">
      <h2 id="campaign-create-title">{tr('Tạo chiến dịch', 'Create campaign')}</h2>
      {evaluated.isLoading && <p role="status">{tr('Đang tải cơ hội…', 'Loading opportunities…')}</p>}
      {evaluated.error && <p role="alert">{tr('Không thể tải danh sách cơ hội.', 'Unable to load opportunities.')}</p>}
      {evaluated.data?.length === 0 && <p className="muted">{tr('Chưa có cơ hội nào ở trạng thái "đã đánh giá". Hãy chấm điểm một cơ hội ở trang Cơ hội trước.', 'No evaluated opportunity yet. Score one on the Opportunities page first.')}</p>}
      <label className="field">{tr('Cơ hội đã đánh giá', 'Evaluated opportunity')}<select value={form.opportunity_id} onChange={set('opportunity_id')} required>
        <option value="">{tr('— Chọn —', '— Choose —')}</option>{evaluated.data?.map(item => <option key={item.id} value={item.id}>{item.title} · {item.business_model} · {item.score ?? '—'}</option>)}</select></label>
      <label className="field">{tr('Tên chiến dịch', 'Campaign name')}<input value={form.name} onChange={set('name')} maxLength={200} required/></label>
      <label className="field">{tr('Ngách', 'Niche')}<input value={form.niche} onChange={set('niche')} maxLength={200}/></label>
      <label className="field">{tr('Khách hàng mục tiêu', 'Target audience')}<input value={form.target_audience} onChange={set('target_audience')} maxLength={500}/></label>
      <label className="field">{tr('Mục tiêu', 'Goal')}<textarea value={form.goal} onChange={set('goal')} maxLength={2000}/></label>
      <label className="field">{tr('Trần chi phí AI của chiến dịch (USD)', 'Campaign AI cost limit (USD)')}<input type="number" min="0.000001" max="45" step="0.000001" value={form.max_cost_usd} onChange={set('max_cost_usd')} required/></label>
      <button className="primary" disabled={api.busy}>{tr('Tạo chiến dịch', 'Create campaign')}</button>
    </form>
    {error && <p className="form-error" role="alert">{error}</p>}{success && <p role="status">{success}</p>}
    <section className="data-section" aria-labelledby="campaign-list-title"><h2 id="campaign-list-title">{tr('Danh sách chiến dịch', 'Campaigns')}</h2>
      {campaigns.isLoading && <p role="status">{tr('Đang tải…', 'Loading…')}</p>}
      {campaigns.error && <p role="alert">{tr('Không thể tải chiến dịch.', 'Unable to load campaigns.')} <button onClick={() => void campaigns.refetch()}>{tr('Thử lại', 'Retry')}</button></p>}
      <div className="table">{campaigns.data?.length === 0 && <p className="empty">{tr('Chưa có chiến dịch.', 'No campaigns yet.')}</p>}
        {campaigns.data?.map(item => <div className="row" key={item.id}><div><b>{item.name}</b><small>{item.niche ?? '—'} · {item.max_cost_usd} USD · {new Date(item.created_at).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })}</small></div>
          <span className="badge">{item.status}</span><button aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}>{tr('Mở', 'Open')}</button></div>)}</div>
    </section>
    {selected && campaigns.data?.find(item => item.id === selected) && <CampaignDetail api={api} campaign={campaigns.data.find(item => item.id === selected)!}/>}
  </section>;
}
