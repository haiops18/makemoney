import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { linkSchema, type useCampaignApi, useTr } from './campaignApi';

type Api = ReturnType<typeof useCampaignApi>;
const productSchema = z.object({ product_id: z.string(), name: z.string(), url: z.string(), merchant: z.string(), price: z.number().nullable(), discount: z.number().nullable(), image: z.string().nullable() });
type Product = z.infer<typeof productSchema>;
const importSchema = z.object({ program_id: z.string().uuid(), links: z.array(linkSchema), skipped: z.array(z.string()) });
const attestationSchema = z.object({ id: z.string().uuid(), check_name: z.enum(['MEDIA_RIGHTS', 'LEGAL_ADS_TAX']), note: z.string(), attested_by: z.string(), attested_at: z.string() });

/** Pull products from ACCESSTRADE and create tracking links for the chosen ones. */
export function AccesstradeImport({ api, campaignId, editable }: { api: Api; campaignId: string; editable: boolean }) {
  const { tr, locale } = useTr();
  const [merchant, setMerchant] = useState('shopee');
  const [products, setProducts] = useState<Product[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setMessage(null); setLoading(true);
    try {
      setProducts(z.array(productSchema).parse(await api.request(`/campaigns/${campaignId}/accesstrade/products?merchant=${encodeURIComponent(merchant)}&limit=20`)));
      setChosen([]);
    } catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không tải được sản phẩm.', 'Could not load products.') }); }
    finally { setLoading(false); }
  }

  async function importChosen() {
    setMessage(null);
    const picked = (products ?? []).filter(item => chosen.includes(item.product_id)).map(({ product_id, name, url, price, discount }) => ({ product_id, name, url, price, discount }));
    try {
      const result = await api.send('POST', `/campaigns/${campaignId}/accesstrade/import`, { merchant, products: picked }, importSchema);
      setMessage({ error: false, text: tr(`Đã tạo ${result.links.length} link affiliate.`, `Created ${result.links.length} affiliate links.`) + (result.skipped.length ? tr(` Bỏ qua ${result.skipped.length} (đã có link hoặc lỗi).`, ` Skipped ${result.skipped.length}.`) : '') });
      setChosen([]);
    } catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không tạo được link.', 'Could not create links.') }); }
  }

  const price = (item: Product) => item.discount ?? item.price;
  return <section className="panel"><h3>{tr('Lấy sản phẩm từ ACCESSTRADE', 'Products from ACCESSTRADE')}</h3>
    <p className="muted">{tr('Tải danh sách sản phẩm (miễn phí), chọn sản phẩm rồi bấm tạo link: app gọi ACCESSTRADE để tạo link affiliate có theo dõi và lưu giá kèm thời điểm lấy.',
      'Load products (free), pick some, and the app asks ACCESSTRADE for tracked affiliate links and stores the price with its time.')}</p>
    <div className="toolbar"><label className="field">{tr('Nhà bán / chiến dịch', 'Merchant')}<input value={merchant} maxLength={50} pattern="[A-Za-z0-9 ._\-]+" onChange={event => setMerchant(event.target.value.trim())}/></label>
      <button type="button" disabled={loading || merchant.length < 2} onClick={() => void load()}>{loading ? tr('Đang tải…', 'Loading…') : tr('Tải sản phẩm', 'Load products')}</button></div>
    {products?.length === 0 && <p className="empty">{tr('Không có sản phẩm.', 'No products.')}</p>}
    {products && products.length > 0 && <>
      <ul className="table">{products.map(item => <li key={item.product_id}><label className="login-remember">
        <input type="checkbox" checked={chosen.includes(item.product_id)} disabled={!chosen.includes(item.product_id) && chosen.length >= 10}
          onChange={event => setChosen(event.target.checked ? [...chosen, item.product_id] : chosen.filter(id => id !== item.product_id))}/>
        {item.name}{price(item) ? ` · ${price(item)!.toLocaleString(locale)}đ` : ''}</label></li>)}</ul>
      <button className="primary" disabled={api.busy || !editable || !chosen.length} onClick={() => void importChosen()}>{tr(`Tạo link cho ${chosen.length} sản phẩm`, `Create links for ${chosen.length}`)}</button>
    </>}
    {message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
  </section>;
}

/** The Owner's one-time confirmations for the checks that always need the Owner. */
export function StandingAttestations({ api, campaignId, editable }: { api: Api; campaignId: string; editable: boolean }) {
  const { tr } = useTr();
  const list = useQuery({ queryKey: ['campaigns', campaignId, 'attestations'], queryFn: async () => z.array(attestationSchema).parse(await api.request(`/campaigns/${campaignId}/attestations`)) });
  const [notes, setNotes] = useState({ MEDIA_RIGHTS: '', LEGAL_ADS_TAX: '' });
  const [error, setError] = useState('');
  const labels = { MEDIA_RIGHTS: tr('Tôi có quyền dùng mọi hình ảnh, video, tài liệu đăng kèm bài của chiến dịch này', 'I have the rights to every image, video and document posted with this campaign'),
    LEGAL_ADS_TAX: tr('Bài đăng tuân thủ quy định quảng cáo, TMĐT, chính sách nền tảng và tôi kê khai thuế thu nhập affiliate', 'Posts follow advertising, e-commerce and platform rules, and I declare affiliate income for tax') };
  async function attest(check: 'MEDIA_RIGHTS' | 'LEGAL_ADS_TAX') {
    setError('');
    try { await api.send('POST', `/campaigns/${campaignId}/attestations`, { check_name: check, note: notes[check] }, attestationSchema); setNotes({ ...notes, [check]: '' }); }
    catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không lưu được.', 'Unable to save.')); }
  }
  async function revoke(check: string) {
    setError('');
    try { await api.send('POST', `/campaigns/${campaignId}/attestations/${check}/revoke`, {}, z.object({ items: z.array(attestationSchema) })); }
    catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không lưu được.', 'Unable to save.')); }
  }
  return <section className="panel"><h3>{tr('Xác nhận chung cho chiến dịch', 'Campaign-wide confirmations')}</h3>
    <p className="muted">{tr('Xác nhận một lần thay vì cho từng bài. Áp dụng cho các lần kiểm tra sau đó; anh/chị có thể thu hồi bất cứ lúc nào.',
      'Confirm once instead of per item. Applies to checks run afterwards; you can revoke it at any time.')}</p>
    {(['MEDIA_RIGHTS', 'LEGAL_ADS_TAX'] as const).map(check => {
      const current = list.data?.find(item => item.check_name === check);
      return <div key={check}><p><b>{labels[check]}</b></p>
        {current ? <p role="status">✓ {current.note} <button type="button" disabled={api.busy || !editable} onClick={() => void revoke(check)}>{tr('Thu hồi', 'Revoke')}</button></p>
          : <div className="toolbar"><label className="field">{tr('Ghi chú xác nhận', 'Confirmation note')}<input value={notes[check]} maxLength={1000} onChange={event => setNotes({ ...notes, [check]: event.target.value })}/></label>
            <button type="button" disabled={api.busy || !editable || notes[check].trim().length < 3} onClick={() => void attest(check)}>{tr('Xác nhận', 'Confirm')}</button></div>}
      </div>;
    })}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>;
}

const scheduleSchema = z.object({ configured: z.boolean(), integration_id: z.string().uuid().nullable().optional(), enabled: z.boolean(), hours: z.array(z.number()),
  paused_reason: z.string().nullable().optional(), updated_at: z.string().nullable().optional() });
const postSchema = z.object({ id: z.string().uuid(), content_id: z.string().uuid(), version_no: z.number(), slot_at: z.string(), status: z.string(), attempted_at: z.string().nullable(),
  external_post_id: z.string().nullable(), error: z.string().nullable(), title: z.string().nullable() });
const pageSchema = z.array(z.object({ id: z.string().uuid(), kind: z.string(), label: z.string(), last_check_status: z.string().nullable() }));
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

/** The Owner's posting schedule: approved items of this campaign post to the Facebook Page at these hours. */
export function PostingSchedule({ api, campaignId, active }: { api: Api; campaignId: string; active: boolean }) {
  const { tr, locale } = useTr();
  const schedule = useQuery({ queryKey: ['campaigns', campaignId, 'schedule'], queryFn: async () => scheduleSchema.parse(await api.request(`/campaigns/${campaignId}/schedule`)) });
  const posts = useQuery({ queryKey: ['campaigns', campaignId, 'scheduled-posts'], refetchInterval: 15000, queryFn: async () => z.array(postSchema).parse(await api.request(`/campaigns/${campaignId}/scheduled-posts`)) });
  const pages = useQuery({ queryKey: ['campaigns', 'integrations', 'pages'], queryFn: async () => pageSchema.parse(await api.request('/integrations')).filter(item => item.kind === 'FACEBOOK_PAGE') });
  const [page, setPage] = useState('');
  const [hours, setHours] = useState<number[] | null>(null);
  const [error, setError] = useState('');
  const current = schedule.data;
  const chosenHours = hours ?? (current?.configured ? current.hours : [8, 20]);
  const chosenPage = page || current?.integration_id || pages.data?.[0]?.id || '';
  const statusLabel: Record<string, string> = { QUEUED: tr('Chờ đăng', 'Queued'), POSTING: tr('Đang đăng', 'Posting'), POSTED: tr('Đã đăng', 'Posted'), FAILED: tr('Lỗi', 'Failed'), CANCELLED: tr('Đã hủy', 'Cancelled') };

  async function save(enabled: boolean) {
    setError('');
    if (enabled && !window.confirm(tr(`Bật lịch: app sẽ TỰ ĐỘNG đăng lên Facebook Page các bài anh/chị đã duyệt của chiến dịch này, lúc ${chosenHours.map(h => `${h}h`).join(', ')} (giờ Việt Nam). Mọi lỗi sẽ tự dừng lịch. Tiếp tục?`,
      `Turn on: the app will AUTOMATICALLY post this campaign's approved items to the Facebook Page at ${chosenHours.join(', ')}h (Vietnam time). Any error pauses it. Continue?`))) return;
    try {
      await api.send('PUT', `/campaigns/${campaignId}/schedule`, { integration_id: chosenPage, enabled, hours: chosenHours }, scheduleSchema);
      setHours(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không lưu được lịch.', 'Unable to save the schedule.')); }
  }
  async function cancel(id: string) {
    setError('');
    try { await api.send('POST', `/campaigns/${campaignId}/scheduled-posts/${id}/cancel`, {}, postSchema); }
    catch (caught) { setError(caught instanceof Error ? caught.message : tr('Không hủy được.', 'Unable to cancel.')); }
  }
  const toggleHour = (hour: number) => setHours(chosenHours.includes(hour) ? chosenHours.filter(item => item !== hour) : [...chosenHours, hour].sort((a, b) => a - b));
  return <section className="panel"><h3>{tr('Lịch tự đăng lên Facebook Page', 'Automatic posting to the Facebook Page')}</h3>
    <p className="muted">{tr('Chỉ bài anh/chị đã DUYỆT mới được đăng, đúng phiên bản đã duyệt, mỗi bài một lần. Sửa hoặc từ chối bài sẽ hủy lượt đăng. Lỗi bất kỳ sẽ tự dừng lịch.',
      'Only items you APPROVED post, exactly the approved version, once each. Editing or rejecting cancels it. Any error pauses the schedule.')}</p>
    {pages.data?.length === 0 && <p className="form-error" role="alert">{tr('Chưa kết nối Facebook Page ở trang Kết nối.', 'Connect a Facebook Page on the Integrations page first.')}</p>}
    {current?.configured && <p role="status"><span className="badge">{current.enabled ? tr('Đang bật', 'On') : tr('Đang tắt', 'Off')}</span>
      {current.paused_reason && <span className="form-error"> {tr('Đã tự dừng', 'Paused')}: {current.paused_reason}</span>}</p>}
    {pages.data && pages.data.length > 0 && <>
      <label className="field">Facebook Page<select value={chosenPage} onChange={event => setPage(event.target.value)}>
        {pages.data.map(item => <option key={item.id} value={item.id}>{item.label}{item.last_check_status === 'OK' ? '' : tr(' (chưa kiểm tra kết nối)', ' (not checked)')}</option>)}</select></label>
      <fieldset className="field"><legend>{tr('Giờ đăng (giờ Việt Nam, tối đa 6)', 'Posting hours (Vietnam time, up to 6)')}</legend>
        <div className="toolbar">{HOURS.map(hour => <label key={hour} className="login-remember"><input type="checkbox" checked={chosenHours.includes(hour)}
          disabled={!chosenHours.includes(hour) && chosenHours.length >= 6} onChange={() => toggleHour(hour)}/>{hour}h</label>)}</div></fieldset>
      <div className="toolbar">
        <button className="primary" disabled={api.busy || !active || !chosenPage || !chosenHours.length} onClick={() => void save(true)}>{current?.enabled ? tr('Lưu lịch', 'Save schedule') : tr('Bật lịch tự đăng', 'Turn on')}</button>
        {current?.enabled && <button className="danger" disabled={api.busy} onClick={() => void save(false)}>{tr('Tạm dừng', 'Pause')}</button>}</div>
    </>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {posts.data && posts.data.length > 0 && <><h4>{tr('Lượt đăng', 'Posts')}</h4><ul className="table">{posts.data.map(post => <li key={post.id} data-testid="scheduled-post">
      {new Date(post.slot_at).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })} · {post.title ?? post.content_id} · <span className="badge">{statusLabel[post.status] ?? post.status}</span>
      {post.external_post_id && <span className="muted"> · facebook.com/{post.external_post_id}</span>}{post.error && <span className="muted"> · {post.error}</span>}
      {post.status === 'QUEUED' && <> <button type="button" disabled={api.busy} onClick={() => void cancel(post.id)}>{tr('Hủy', 'Cancel')}</button></>}</li>)}</ul></>}
  </section>;
}
