import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { type Evidence, evidenceLabel, linkSchema, productSchema, programSchema, sourceSchema, termSchema, type useCampaignApi, useTr } from './campaignApi';

type Api = ReturnType<typeof useCampaignApi>;
type Props = { api: Api; campaignId: string; readOnly: boolean };
const TERMS = ['COMMISSION_RATE', 'COMMISSION_CAP', 'COMMISSION_MODEL', 'COOKIE_DAYS', 'ATTRIBUTION', 'PAYOUT', 'REFUND_CANCELLATION', 'TAX_WITHHOLDING', 'JOIN_CONDITIONS'] as const;
const UNITS = ['NONE', 'PERCENT', 'VND', 'USD', 'DAYS'] as const;
const NETWORKS = ['SHOPEE', 'TIKTOK_SHOP', 'ACCESSTRADE', 'ECOMOBI', 'LAZADA', 'OTHER'] as const;
const list = (value: string) => value.split(/[\s,]+/).map(item => item.trim()).filter(Boolean);

function useFeedback() {
  const { tr } = useTr();
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  async function run(action: () => Promise<unknown>, done: string): Promise<boolean> {
    setMessage(null);
    try { await action(); setMessage({ error: false, text: done }); return true; } catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không thể lưu.', 'Could not save.') }); return false; }
  }
  const view = message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>;
  return { run, view };
}

function useList<T>(api: Api, campaignId: string, name: string, schema: z.ZodType<T>) {
  return useQuery({ queryKey: ['campaigns', campaignId, name], queryFn: async () => z.array(schema).parse(await api.request(`/campaigns/${campaignId}/${name}`)) });
}

function Loading({ query }: { query: { isLoading: boolean; error: unknown; refetch: () => unknown } }) {
  const { tr } = useTr();
  if (query.isLoading) return <p role="status">{tr('Đang tải…', 'Loading…')}</p>;
  if (query.error) return <p role="alert">{tr('Không thể tải dữ liệu.', 'Unable to load data.')} <button onClick={() => void query.refetch()}>{tr('Thử lại', 'Retry')}</button></p>;
  return null;
}

const EvidenceBadge = ({ status }: { status: Evidence }) => { const { tr } = useTr(); return <span className={status === 'VERIFIED' ? 'badge badge-approved' : status === 'REJECTED' ? 'badge badge-rejected' : 'badge badge-pending'}>{evidenceLabel(status, tr)}</span>; };

export function CampaignSources({ api, campaignId, readOnly }: Props) {
  const { tr } = useTr();
  const sources = useList(api, campaignId, 'sources', sourceSchema);
  const feedback = useFeedback();
  const [form, setForm] = useState({ source_name: '', source_url: '', excerpt: '', captured_at: new Date().toISOString().slice(0, 10) });
  const [notes, setNotes] = useState<Record<string, string>>({});
  async function add(event: React.FormEvent) {
    event.preventDefault();
    const body = { source_name: form.source_name.trim(), source_url: form.source_url.trim() || null, excerpt: form.excerpt.trim(), captured_at: new Date(`${form.captured_at}T00:00:00+07:00`).toISOString() };
    if (await feedback.run(() => api.send('POST', `/campaigns/${campaignId}/sources`, body, sourceSchema), tr('Đã thêm nguồn (chưa xác minh).', 'Source added (unverified).'))) setForm({ ...form, source_name: '', source_url: '', excerpt: '' });
  }
  return <>
    <p className="muted">{tr('App không tự mở link nguồn. Chỉ nguồn anh/chị đã xác minh mới được dùng như sự thật; quyết định xác minh không đổi được.', 'The app never opens source links. Only sources you verify count as facts; the decision is final.')}</p>
    {!readOnly && <form onSubmit={event => void add(event)}>
      <label className="field">{tr('Tên nguồn', 'Source name')}<input value={form.source_name} onChange={event => setForm({ ...form, source_name: event.target.value })} maxLength={200} required/></label>
      <label className="field">URL<input type="url" value={form.source_url} onChange={event => setForm({ ...form, source_url: event.target.value })} maxLength={2048}/></label>
      <label className="field">{tr('Trích đoạn', 'Excerpt')}<textarea value={form.excerpt} onChange={event => setForm({ ...form, excerpt: event.target.value })} maxLength={12000} required/></label>
      <label className="field">{tr('Ngày thu thập', 'Captured on')}<input type="date" value={form.captured_at} max={new Date().toISOString().slice(0, 10)} onChange={event => setForm({ ...form, captured_at: event.target.value })} required/></label>
      <button disabled={api.busy}>{tr('Thêm nguồn', 'Add source')}</button>
    </form>}
    {feedback.view}<Loading query={sources}/>
    {sources.data?.length === 0 && <p className="empty">{tr('Chưa có nguồn.', 'No sources yet.')}</p>}
    <div className="table">{sources.data?.map(item => <div className="row" key={item.id}><div><b>{item.source_name}</b><small>{item.source_url ?? '—'} · {item.captured_at.slice(0, 10)}</small><small>{item.excerpt}</small>
      {item.verification_status !== 'UNVERIFIED' && <small>{item.verified_by} · {item.verification_note}</small>}
      {item.verification_status === 'UNVERIFIED' && !readOnly && <div className="actions"><label className="field">{tr('Ghi chú xác minh', 'Verification note')}<input value={notes[item.id] ?? ''} maxLength={1000} onChange={event => setNotes({ ...notes, [item.id]: event.target.value })}/></label>
        {(['VERIFIED', 'REJECTED'] as const).map(status => <button key={status} className={status === 'REJECTED' ? 'danger' : ''} disabled={api.busy || !(notes[item.id] ?? '').trim()}
          onClick={() => { if (window.confirm(tr('Quyết định này không thể thay đổi. Tiếp tục?', 'This decision is final. Continue?'))) void feedback.run(() => api.send('POST', `/campaigns/${campaignId}/sources/${item.id}/verification`, { status, note: (notes[item.id] ?? '').trim() }, sourceSchema), tr('Đã ghi nhận.', 'Recorded.')); }}>
          {status === 'VERIFIED' ? tr('Xác minh', 'Verify') : tr('Từ chối', 'Reject')}</button>)}</div>}
    </div><EvidenceBadge status={item.verification_status}/></div>)}</div>
  </>;
}

function SourcePicker({ api, campaignId, value, onChange, label }: { api: Api; campaignId: string; value: string; onChange: (value: string) => void; label: string }) {
  const { tr } = useTr();
  const sources = useList(api, campaignId, 'sources', sourceSchema);
  return <label className="field">{label}<select value={value} onChange={event => onChange(event.target.value)}>
    <option value="">{tr('— Không có nguồn —', '— No source —')}</option>
    {sources.data?.filter(item => item.verification_status !== 'REJECTED').map(item => <option key={item.id} value={item.id}>{item.source_name} · {item.verification_status === 'VERIFIED' ? tr('đã xác minh', 'verified') : tr('chưa xác minh', 'unverified')}</option>)}
  </select></label>;
}

export function CampaignPrograms({ api, campaignId, readOnly }: Props) {
  const { tr } = useTr();
  const programs = useList(api, campaignId, 'programs', programSchema);
  const feedback = useFeedback();
  const [form, setForm] = useState({ network: 'SHOPEE', name: '', join_url: '', link_hosts: '', tracking_param_keys: '' });
  const [term, setTerm] = useState({ program_id: '', term: 'COMMISSION_RATE', value_text: '', value_numeric: '', unit: 'NONE', source_id: '' });
  async function addProgram(event: React.FormEvent) {
    event.preventDefault();
    const body = { network: form.network, name: form.name.trim(), join_url: form.join_url.trim() || null, link_hosts: list(form.link_hosts), tracking_param_keys: list(form.tracking_param_keys) };
    if (await feedback.run(() => api.send('POST', `/campaigns/${campaignId}/programs`, body, programSchema), tr('Đã thêm chương trình.', 'Program added.'))) setForm({ ...form, name: '', join_url: '', link_hosts: '', tracking_param_keys: '' });
  }
  async function addTerm(event: React.FormEvent) {
    event.preventDefault();
    const body = { term: term.term, value_text: term.value_text.trim(), value_numeric: term.unit === 'NONE' ? null : term.value_numeric.trim(), unit: term.unit, source_id: term.source_id || null };
    if (await feedback.run(() => api.send('POST', `/campaigns/${campaignId}/programs/${term.program_id}/terms`, body, termSchema), tr('Đã ghi điều khoản.', 'Term recorded.'))) setTerm({ ...term, value_text: '', value_numeric: '' });
  }
  return <>
    <p className="muted">{tr('Mỗi chương trình có danh sách tên miền link được phép và các tham số theo dõi được thêm. Điều khoản ghi thêm (không sửa); bản mới nhất có hiệu lực.', 'Each program lists allowed link hosts and tracking keys. Terms are append-only; the newest applies.')}</p>
    {!readOnly && <form onSubmit={event => void addProgram(event)}>
      <label className="field">{tr('Mạng affiliate', 'Network')}<select value={form.network} onChange={event => setForm({ ...form, network: event.target.value })}>{NETWORKS.map(item => <option key={item}>{item}</option>)}</select></label>
      <label className="field">{tr('Tên chương trình', 'Program name')}<input value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} maxLength={200} required/></label>
      <label className="field">{tr('Link đăng ký chương trình', 'Program join URL')}<input type="url" value={form.join_url} onChange={event => setForm({ ...form, join_url: event.target.value })} maxLength={2048}/></label>
      <label className="field">{tr('Tên miền link được phép (cách nhau bằng dấu phẩy)', 'Allowed link hosts (comma separated)')}<input value={form.link_hosts} onChange={event => setForm({ ...form, link_hosts: event.target.value })} placeholder="s.shopee.vn, shope.ee" required/></label>
      <label className="field">{tr('Tham số theo dõi được thêm (tuỳ chọn)', 'Tracking keys the app may add (optional)')}<input value={form.tracking_param_keys} onChange={event => setForm({ ...form, tracking_param_keys: event.target.value })} placeholder="sub_id"/></label>
      <button disabled={api.busy}>{tr('Thêm chương trình', 'Add program')}</button>
    </form>}
    {feedback.view}<Loading query={programs}/>
    {programs.data?.length === 0 && <p className="empty">{tr('Chưa có chương trình affiliate.', 'No affiliate programs yet.')}</p>}
    {programs.data?.map(program => <article className="panel" key={program.id}><h3>{program.name} <span className="badge">{program.network}</span></h3>
      <p className="muted">{tr('Tên miền', 'Hosts')}: {program.link_hosts.join(', ')} · {tr('Tham số', 'Keys')}: {program.tracking_param_keys.join(', ') || '—'}</p>
      <div className="table">{program.terms.length === 0 && <p className="empty">{tr('Chưa có điều khoản.', 'No terms yet.')}</p>}
        {program.terms.map(item => <div className="row" key={item.id}><div><b>{item.term}</b><small>{item.value_text}{item.value_numeric !== null ? ` · ${item.value_numeric} ${item.unit}` : ''}</small></div><EvidenceBadge status={item.evidence_status}/></div>)}</div>
    </article>)}
    {!readOnly && !!programs.data?.length && <form className="panel" onSubmit={event => void addTerm(event)}><h3>{tr('Ghi điều khoản', 'Record a term')}</h3>
      <label className="field">{tr('Chương trình', 'Program')}<select value={term.program_id} onChange={event => setTerm({ ...term, program_id: event.target.value })} required><option value="">{tr('— Chọn —', '— Choose —')}</option>{programs.data.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="field">{tr('Loại điều khoản', 'Term')}<select value={term.term} onChange={event => setTerm({ ...term, term: event.target.value })}>{TERMS.map(item => <option key={item}>{item}</option>)}</select></label>
      <label className="field">{tr('Nội dung', 'Value')}<input value={term.value_text} onChange={event => setTerm({ ...term, value_text: event.target.value })} maxLength={1000} required/></label>
      <label className="field">{tr('Đơn vị số', 'Numeric unit')}<select value={term.unit} onChange={event => setTerm({ ...term, unit: event.target.value })}>{UNITS.map(item => <option key={item}>{item}</option>)}</select></label>
      {term.unit !== 'NONE' && <label className="field">{tr('Giá trị số', 'Numeric value')}<input inputMode="decimal" pattern="\d{1,12}(\.\d{1,6})?" value={term.value_numeric} onChange={event => setTerm({ ...term, value_numeric: event.target.value })} required/></label>}
      <SourcePicker api={api} campaignId={campaignId} value={term.source_id} onChange={source_id => setTerm({ ...term, source_id })} label={tr('Nguồn', 'Source')}/>
      <button disabled={api.busy}>{tr('Ghi điều khoản', 'Record term')}</button>
    </form>}
  </>;
}

export function CampaignProducts({ api, campaignId, readOnly }: Props) {
  const { tr } = useTr();
  const products = useList(api, campaignId, 'products', productSchema);
  const feedback = useFeedback();
  const [form, setForm] = useState({ name: '', merchant: '', product_url: '', price_text: '', price_source_id: '' });
  async function add(event: React.FormEvent) {
    event.preventDefault();
    const body = { name: form.name.trim(), merchant: form.merchant.trim() || null, product_url: form.product_url.trim() || null, price_text: form.price_text.trim() || null, price_source_id: form.price_source_id || null };
    if (await feedback.run(() => api.send('POST', `/campaigns/${campaignId}/products`, body, productSchema), tr('Đã thêm sản phẩm.', 'Product added.'))) setForm({ name: '', merchant: '', product_url: '', price_text: '', price_source_id: '' });
  }
  return <>
    {!readOnly && <form onSubmit={event => void add(event)}>
      <label className="field">{tr('Tên sản phẩm', 'Product name')}<input value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} maxLength={300} required/></label>
      <label className="field">{tr('Shop / merchant', 'Merchant')}<input value={form.merchant} onChange={event => setForm({ ...form, merchant: event.target.value })} maxLength={200}/></label>
      <label className="field">{tr('Link sản phẩm', 'Product URL')}<input type="url" value={form.product_url} onChange={event => setForm({ ...form, product_url: event.target.value })} maxLength={2048}/></label>
      <label className="field">{tr('Giá (cần nguồn)', 'Price (needs a source)')}<input value={form.price_text} onChange={event => setForm({ ...form, price_text: event.target.value })} maxLength={100}/></label>
      <SourcePicker api={api} campaignId={campaignId} value={form.price_source_id} onChange={price_source_id => setForm({ ...form, price_source_id })} label={tr('Nguồn của giá', 'Price source')}/>
      <button disabled={api.busy || (!!form.price_text.trim() && !form.price_source_id)}>{tr('Thêm sản phẩm', 'Add product')}</button>
    </form>}
    {feedback.view}<Loading query={products}/>
    {products.data?.length === 0 && <p className="empty">{tr('Chưa có sản phẩm.', 'No products yet.')}</p>}
    <div className="table">{products.data?.map(item => <div className="row" key={item.id}><div><b>{item.name}</b><small>{item.merchant ?? '—'} · {item.price_text ?? tr('chưa có giá', 'no price')}</small></div>{item.price_text && <EvidenceBadge status={item.price_evidence_status}/>}</div>)}</div>
  </>;
}

export function CampaignLinks({ api, campaignId, readOnly }: Props) {
  const { tr } = useTr();
  const links = useList(api, campaignId, 'links', linkSchema);
  const programs = useList(api, campaignId, 'programs', programSchema);
  const products = useList(api, campaignId, 'products', productSchema);
  const feedback = useFeedback();
  const [form, setForm] = useState({ program_id: '', product_id: '', label: '', original_url: '', tracking: '' });
  const program = programs.data?.find(item => item.id === form.program_id);
  async function add(event: React.FormEvent) {
    event.preventDefault();
    const tracking = Object.fromEntries(list(form.tracking).map(pair => pair.split('=', 2) as [string, string]));
    const body = { program_id: form.program_id, product_id: form.product_id || null, label: form.label.trim(), original_url: form.original_url.trim(), tracking_params: tracking };
    if (await feedback.run(() => api.send('POST', `/campaigns/${campaignId}/links`, body, linkSchema), tr('Đã lưu link.', 'Link saved.'))) setForm({ ...form, label: '', original_url: '', tracking: '' });
  }
  return <>
    <p className="muted">{tr('Dán link affiliate anh/chị lấy từ trang của sàn. App chỉ kiểm tra tên miền, thêm tham số được phép và giữ nguyên link gốc; app không mở hay chia sẻ link.', 'Paste the affiliate link from the network. The app only checks the host, appends allowed keys and keeps the original; it never opens or shares links.')}</p>
    {!readOnly && <form onSubmit={event => void add(event)}>
      <label className="field">{tr('Chương trình', 'Program')}<select value={form.program_id} onChange={event => setForm({ ...form, program_id: event.target.value })} required><option value="">{tr('— Chọn —', '— Choose —')}</option>{programs.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="field">{tr('Sản phẩm (tuỳ chọn)', 'Product (optional)')}<select value={form.product_id} onChange={event => setForm({ ...form, product_id: event.target.value })}><option value="">—</option>{products.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="field">{tr('Nhãn', 'Label')}<input value={form.label} onChange={event => setForm({ ...form, label: event.target.value })} maxLength={200} required/></label>
      <label className="field">{tr('Link affiliate gốc (https)', 'Original affiliate link (https)')}<input type="url" value={form.original_url} onChange={event => setForm({ ...form, original_url: event.target.value })} maxLength={2048} required/></label>
      {!!program?.tracking_param_keys.length && <label className="field">{tr(`Tham số theo dõi (dạng key=value; được phép: ${program.tracking_param_keys.join(', ')})`, `Tracking (key=value; allowed: ${program.tracking_param_keys.join(', ')})`)}<input value={form.tracking} onChange={event => setForm({ ...form, tracking: event.target.value })}/></label>}
      <button disabled={api.busy}>{tr('Lưu link', 'Save link')}</button>
    </form>}
    {feedback.view}<Loading query={links}/>
    {links.data?.length === 0 && <p className="empty">{tr('Chưa có link.', 'No links yet.')}</p>}
    <div className="table">{links.data?.map(item => <div className="row" key={item.id}><div><b>{item.label}</b><small className="hash">{item.final_url}</small></div>
      <span className={item.status === 'ACTIVE' ? 'badge badge-approved' : 'badge'}>{item.status === 'ACTIVE' ? tr('Đang dùng', 'Active') : tr('Ngừng dùng', 'Retired')}</span>
      {item.status === 'ACTIVE' && !readOnly && <button disabled={api.busy} onClick={() => { if (window.confirm(tr('Ngừng dùng link này?', 'Retire this link?'))) void feedback.run(() => api.send('POST', `/campaigns/${campaignId}/links/${item.id}/retire`, {}, linkSchema), tr('Đã ngừng dùng link.', 'Link retired.')); }}>{tr('Ngừng dùng', 'Retire')}</button>}
    </div>)}</div>
  </>;
}
