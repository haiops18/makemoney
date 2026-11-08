import { useState } from 'react';
import { type Campaign, campaignSchema, type useCampaignApi, useTr } from './campaignApi';
import CampaignContent from './CampaignContent';
import { CampaignLinks, CampaignProducts, CampaignPrograms, CampaignSources } from './CampaignSetup';

type Api = ReturnType<typeof useCampaignApi>;
const TABS = ['overview', 'sources', 'programs', 'products', 'links', 'content'] as const;
type Tab = typeof TABS[number];
const NEXT: Record<Campaign['status'], Campaign['status'][]> = { DRAFT: ['ACTIVE', 'ARCHIVED'], ACTIVE: ['PAUSED', 'ARCHIVED'], PAUSED: ['ACTIVE', 'ARCHIVED'], ARCHIVED: [] };

export default function CampaignDetail({ api, campaign }: { api: Api; campaign: Campaign }) {
  const { tr } = useTr();
  const [tab, setTab] = useState<Tab>('overview');
  const labels: Record<Tab, string> = { overview: tr('Tổng quan', 'Overview'), sources: tr('Nguồn', 'Sources'), programs: tr('Chương trình & điều khoản', 'Programs & terms'), products: tr('Sản phẩm', 'Products'), links: tr('Link affiliate', 'Affiliate links'), content: tr('Nội dung', 'Content') };
  const readOnly = campaign.status === 'ARCHIVED';
  return <section className="panel" aria-labelledby="campaign-detail-title">
    <h2 id="campaign-detail-title">{campaign.name} <span className="badge">{campaign.status}</span></h2>
    <div className="toolbar" role="tablist" aria-label={tr('Mục của chiến dịch', 'Campaign sections')}>
      {TABS.map(item => <button key={item} role="tab" id={`campaign-tab-${item}`} aria-selected={tab === item} aria-controls={`campaign-panel-${item}`} className={tab === item ? 'primary' : ''} onClick={() => setTab(item)}>{labels[item]}</button>)}
    </div>
    {readOnly && <p className="muted">{tr('Chiến dịch đã lưu trữ: chỉ xem, không sửa được.', 'Archived campaign: read-only.')}</p>}
    <div role="tabpanel" id={`campaign-panel-${tab}`} aria-labelledby={`campaign-tab-${tab}`}>
      {tab === 'overview' && <Overview api={api} campaign={campaign}/>}
      {tab === 'sources' && <CampaignSources api={api} campaignId={campaign.id} readOnly={readOnly}/>}
      {tab === 'programs' && <CampaignPrograms api={api} campaignId={campaign.id} readOnly={readOnly}/>}
      {tab === 'products' && <CampaignProducts api={api} campaignId={campaign.id} readOnly={readOnly}/>}
      {tab === 'links' && <CampaignLinks api={api} campaignId={campaign.id} readOnly={readOnly}/>}
      {tab === 'content' && <CampaignContent api={api} campaignId={campaign.id} campaignStatus={campaign.status}/>}
    </div>
  </section>;
}

function Overview({ api, campaign }: { api: Api; campaign: Campaign }) {
  const { tr } = useTr();
  const [disclosure, setDisclosure] = useState(campaign.disclosure_text ?? '');
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const path = `/campaigns/${campaign.id}`;
  async function run(action: () => Promise<unknown>, done: string) {
    setMessage(null);
    try { await action(); setMessage({ error: false, text: done }); } catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không thể lưu.', 'Could not save.') }); }
  }
  const statusLabel: Record<Campaign['status'], string> = { DRAFT: tr('Nháp', 'Draft'), ACTIVE: tr('Kích hoạt', 'Activate'), PAUSED: tr('Tạm dừng', 'Pause'), ARCHIVED: tr('Lưu trữ', 'Archive') };
  return <>
    <dl className="details">
      <dt>{tr('Mô hình', 'Business model')}</dt><dd>{campaign.business_model}</dd>
      <dt>{tr('Ngách', 'Niche')}</dt><dd>{campaign.niche ?? '—'}</dd>
      <dt>{tr('Khách hàng', 'Audience')}</dt><dd>{campaign.target_audience ?? '—'}</dd>
      <dt>{tr('Mục tiêu', 'Goal')}</dt><dd>{campaign.goal ?? '—'}</dd>
      <dt>{tr('Trần chi phí AI', 'AI cost limit')}</dt><dd>{campaign.max_cost_usd} USD</dd>
    </dl>
    <form onSubmit={event => { event.preventDefault(); void run(() => api.send('PATCH', path, { version: campaign.version, disclosure_text: disclosure.trim() }, campaignSchema), tr('Đã lưu câu công bố.', 'Disclosure saved.')); }}>
      <label className="field">{tr('Câu công bố affiliate (tuỳ chọn)', 'Affiliate disclosure (optional)')}
        <textarea value={disclosure} onChange={event => setDisclosure(event.target.value)} maxLength={500} disabled={campaign.status === 'ARCHIVED'}/></label>
      <p className="muted">{tr('Không có câu mặc định. Nếu để trống, bước kiểm tra công bố của mỗi nội dung sẽ chờ anh/chị xác nhận.', 'There is no default. If empty, the disclosure check on each item waits for your confirmation.')}</p>
      <button disabled={api.busy || campaign.status === 'ARCHIVED'}>{tr('Lưu câu công bố', 'Save disclosure')}</button>
    </form>
    <div className="toolbar">{NEXT[campaign.status].map(status => <button key={status} className={status === 'ARCHIVED' ? 'danger' : ''} disabled={api.busy}
      onClick={() => { if (status !== 'ARCHIVED' || window.confirm(tr('Lưu trữ chiến dịch? Sau đó không sửa được nữa.', 'Archive this campaign? It becomes read-only.'))) void run(() => api.send('POST', `${path}/status`, { version: campaign.version, status }, campaignSchema), tr('Đã đổi trạng thái.', 'Status changed.')); }}>{statusLabel[status]}</button>)}</div>
    {message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
  </>;
}
