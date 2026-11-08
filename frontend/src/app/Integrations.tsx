import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { useCampaignApi, useTr, type Tr } from './campaignApi';

const KINDS = ['SEARCH_TAVILY', 'SEARCH_BRAVE', 'ACCESSTRADE', 'FACEBOOK_PAGE'] as const;
type Kind = typeof KINDS[number];
const integrationSchema = z.object({
  id: z.string().uuid(), kind: z.enum(KINDS), label: z.string(), purpose: z.string(), config: z.record(z.string(), z.string()), has_secret: z.boolean(), enabled: z.boolean(),
  check_costs: z.boolean(), last_checked_at: z.string().nullable(), last_check_status: z.string().nullable(), last_check_detail: z.string().nullable(),
});
type Integration = z.infer<typeof integrationSchema>;

function info(tr: Tr): Record<Kind, { title: string; help: string; secret: string; group: string }> {
  return {
    SEARCH_TAVILY: { group: tr('Nguồn tìm kiếm web', 'Web search source'), title: 'Tavily', secret: 'API key (tvly-…)',
      help: tr('AI dùng để tự tìm cơ hội trên Internet. Lấy key ở app.tavily.com.', 'Lets the AI search the web for opportunities. Get a key at app.tavily.com.') },
    SEARCH_BRAVE: { group: tr('Nguồn tìm kiếm web', 'Web search source'), title: 'Brave Search', secret: 'Subscription token',
      help: tr('Nguồn tìm kiếm thay thế. Lấy token ở api-dashboard.search.brave.com.', 'Alternative search source. Get a token at api-dashboard.search.brave.com.') },
    ACCESSTRADE: { group: tr('Mạng affiliate', 'Affiliate network'), title: 'ACCESSTRADE', secret: 'Access key',
      help: tr('Lấy sản phẩm, tạo link affiliate (gồm chiến dịch Shopee) và đọc hoa hồng. Key ở pub.accesstrade.vn → Thông tin cá nhân.', 'Products, affiliate links (including Shopee campaigns) and commissions. Key at pub.accesstrade.vn → profile.') },
    FACEBOOK_PAGE: { group: tr('Kênh đăng bài', 'Posting channel'), title: 'Facebook Page', secret: 'Page access token',
      help: tr('Đăng bài đã duyệt theo lịch. Cần Page access token có quyền pages_manage_posts.', 'Posts approved content on schedule. Needs a Page access token with pages_manage_posts.') },
  };
}

export default function Integrations({ token }: { token: string }) {
  const { tr, locale } = useTr();
  const api = useCampaignApi(token);
  const details = info(tr);
  const list = useQuery({ queryKey: ['campaigns', 'integrations'], enabled: !!token, queryFn: async () => z.array(integrationSchema).parse(await api.request('/integrations')) });
  const [kind, setKind] = useState<Kind>('SEARCH_TAVILY');
  const [label, setLabel] = useState('');
  const [secret, setSecret] = useState('');
  const [pageId, setPageId] = useState('');
  const [replacing, setReplacing] = useState<Integration | null>(null);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const statusLabel: Record<string, string> = { OK: tr('Kết nối tốt', 'Connected'), AUTH_FAILED: tr('Sai token hoặc thiếu quyền', 'Token rejected'), RATE_LIMITED: tr('Bị giới hạn tần suất, thử lại sau', 'Rate limited'),
    PROVIDER_ERROR: tr('Dịch vụ báo lỗi', 'Service error'), INVALID_RESPONSE: tr('Phản hồi không khớp (kiểm tra ID)', 'Unexpected response (check the ID)'), UNREACHABLE: tr('Không kết nối được', 'Unreachable') };

  async function run(action: () => Promise<unknown>, done: string) {
    setMessage(null);
    try { await action(); setMessage({ error: false, text: done }); return true; }
    catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không thể lưu.', 'Unable to save.') }); return false; }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const ok = replacing
      ? await run(() => api.send('PATCH', `/integrations/${replacing.id}`, { secret }, integrationSchema), tr('Đã thay token. Hãy kiểm tra kết nối.', 'Token replaced. Check the connection.'))
      : await run(() => api.send('POST', '/integrations', { kind, label: label || details[kind].title, secret, config: kind === 'FACEBOOK_PAGE' ? { page_id: pageId } : {} }, integrationSchema),
        tr('Đã lưu. Token được mã hóa và không hiển thị lại.', 'Saved. The token is encrypted and never shown again.'));
    if (ok) { setSecret(''); setLabel(''); setPageId(''); setReplacing(null); }
  }

  function check(item: Integration) {
    if (item.check_costs && !window.confirm(tr('Kiểm tra sẽ dùng 1 lượt tìm kiếm có tính phí. Tiếp tục?', 'This check uses one paid search query. Continue?'))) return;
    void run(() => api.send('POST', `/integrations/${item.id}/test`, {}, integrationSchema), tr('Đã kiểm tra kết nối.', 'Connection checked.'));
  }

  function remove(item: Integration) {
    if (!window.confirm(tr(`Xóa kết nối "${item.label}"? Token sẽ bị xóa vĩnh viễn.`, `Remove "${item.label}"? The token is deleted permanently.`))) return;
    void run(() => api.send('POST', `/integrations/${item.id}/archive`, {}, integrationSchema), tr('Đã xóa kết nối.', 'Integration removed.'));
  }

  const current = replacing?.kind ?? kind;
  return <section>
    <div className="page-head"><div><p className="eyebrow">{tr('Hồ sơ của anh/chị', 'Your profile')}</p><h1>{tr('Kết nối tài khoản', 'Integrations')}</h1>
      <p>{tr('Nhập một lần các tài khoản app được dùng thay anh/chị. Token được mã hóa ở máy chủ, không bao giờ hiển thị lại hay gửi xuống trình duyệt. Lưu kết nối không tự chạy việc gì.',
        'Enter once the accounts the app may use for you. Tokens are encrypted on the server and never shown again. Saving runs nothing.')}</p></div></div>
    <form className="panel" onSubmit={event => void save(event)}>
      <h3>{replacing ? tr(`Thay token cho "${replacing.label}"`, `Replace the token of "${replacing.label}"`) : tr('Thêm kết nối', 'Add an integration')}</h3>
      {!replacing && <label className="field">{tr('Loại', 'Type')}<select value={kind} onChange={event => setKind(event.target.value as Kind)}>
        {KINDS.map(item => <option key={item} value={item}>{details[item].group} · {details[item].title}</option>)}</select></label>}
      <p className="muted">{details[current].help}</p>
      {!replacing && <label className="field">{tr('Tên gợi nhớ (tuỳ chọn)', 'Name (optional)')}<input value={label} maxLength={100} placeholder={details[kind].title} onChange={event => setLabel(event.target.value)}/></label>}
      {!replacing && kind === 'FACEBOOK_PAGE' && <label className="field">{tr('Page ID (dạng số)', 'Page ID (numeric)')}<input value={pageId} inputMode="numeric" pattern="\d{5,25}" required onChange={event => setPageId(event.target.value.trim())}/></label>}
      <label className="field">{details[current].secret}<input type="password" autoComplete="off" value={secret} maxLength={4096} required onChange={event => setSecret(event.target.value)}/></label>
      <div className="toolbar"><button className="primary" disabled={api.busy || !secret.trim()}>{replacing ? tr('Thay token', 'Replace token') : tr('Lưu kết nối', 'Save integration')}</button>
        {replacing && <button type="button" onClick={() => { setReplacing(null); setSecret(''); }}>{tr('Hủy', 'Cancel')}</button>}</div>
    </form>
    {message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
    <h3>{tr('Đã kết nối', 'Connected accounts')}</h3>
    {list.isLoading && <p role="status">{tr('Đang tải…', 'Loading…')}</p>}
    {list.error && <p role="alert">{tr('Không thể tải danh sách kết nối.', 'Unable to load integrations.')}</p>}
    {list.data?.length === 0 && <p className="empty">{tr('Chưa có kết nối nào.', 'No integrations yet.')}</p>}
    <div className="table">{list.data?.map(item => <article className="panel" key={item.id} data-testid="integration">
      <p><b>{item.label}</b> · {details[item.kind].group} · {details[item.kind].title}{item.config.page_id ? ` · Page ${item.config.page_id}` : ''}</p>
      <p className="muted">{item.has_secret ? tr('Token đã lưu (đã mã hóa)', 'Token stored (encrypted)') : tr('Chưa có token', 'No token')} · {item.last_check_status
        ? `${statusLabel[item.last_check_status] ?? item.last_check_status}${item.last_check_detail ? ` — ${item.last_check_detail}` : ''} · ${item.last_checked_at ? new Date(item.last_checked_at).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' }) : ''}`
        : tr('Chưa kiểm tra', 'Not checked yet')}</p>
      <div className="toolbar"><button disabled={api.busy} onClick={() => check(item)}>{tr('Kiểm tra kết nối', 'Check connection')}</button>
        <button disabled={api.busy} onClick={() => { setReplacing(item); setSecret(''); }}>{tr('Thay token', 'Replace token')}</button>
        <button className="danger" disabled={api.busy} onClick={() => remove(item)}>{tr('Xóa', 'Remove')}</button></div>
    </article>)}</div>
  </section>;
}
