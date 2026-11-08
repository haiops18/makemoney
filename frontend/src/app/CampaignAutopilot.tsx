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
