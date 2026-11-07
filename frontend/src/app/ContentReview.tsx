import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { type useCampaignApi, useTr } from './campaignApi';

type Api = ReturnType<typeof useCampaignApi>;
const claim = z.object({ classification: z.string(), statement: z.string(), source_ids: z.array(z.string()) });
const version = z.object({ version_no: z.number(), base_version_no: z.number().nullable(), title: z.string(), body: z.string(), hashtags: z.array(z.string()), cta: z.string(),
  claims: z.array(claim), author_kind: z.string(), author: z.string(), created_at: z.string() });
const check = z.object({ check_name: z.string(), result: z.enum(['PASS', 'FAIL', 'NEEDS_OWNER']), method: z.string(), note: z.string(), evidence: z.array(z.string()), attested_by: z.string().nullable().optional() });
const record = z.object({ id: z.string().uuid(), channel: z.string(), published_url: z.string(), published_at: z.string() });
export const detailSchema = z.object({ id: z.string().uuid(), content_type: z.string(), status: z.string(), current_version: version, versions: z.array(version), checks: z.array(check),
  publish_records: z.array(record), decided_by: z.string().nullable().optional(), decision_note: z.string().nullable().optional() });
type Detail = z.infer<typeof detailSchema>;
const exportSchema = z.object({ text: z.string(), link_url: z.string(), disclosure_added: z.boolean(), status: z.string(), version_no: z.number() });
const EDITABLE = ['DRAFT', 'CHECK_FAILED', 'IN_REVIEW', 'APPROVED', 'READY_TO_PUBLISH', 'REJECTED'];

/** Level B review of one content item: checks, Owner edits, decision, export and publish record. */
export default function ContentReview({ api, campaignId, contentId }: { api: Api; campaignId: string; contentId: string }) {
  const { tr, locale } = useTr();
  const cache = useQueryClient();
  const path = `/campaigns/${campaignId}/content/${contentId}`;
  const detail = useQuery({ queryKey: ['campaigns', campaignId, 'content', contentId], queryFn: async () => detailSchema.parse(await api.request(path)) });
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const [note, setNote] = useState('');
  const [attest, setAttest] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<null | { title: string; body: string; cta: string; hashtags: string }>(null);
  const [exported, setExported] = useState<z.infer<typeof exportSchema> | null>(null);
  const [publish, setPublish] = useState({ channel: '', published_url: '', published_at: '' });
  const labels: Record<string, string> = { LINK_PLACEHOLDER: tr('Chỗ giữ link', 'Link placeholder'), DISCLOSURE: tr('Công bố affiliate', 'Affiliate disclosure'),
    CLAIM_EVIDENCE: tr('Khẳng định có nguồn', 'Claims have sources'), PRICE_CLAIM: tr('Giá / % khớp nguồn', 'Prices match sources'), PLATFORM_POLICY: tr('Cụm từ bị hạn chế', 'Restricted phrases'),
    EXTRA_LINKS: tr('Địa chỉ web khác', 'Other web addresses'), DUPLICATE: tr('Trùng lặp', 'Duplicate'), MEDIA_RIGHTS: tr('Quyền dùng hình ảnh/tài liệu', 'Media rights'),
    LEGAL_ADS_TAX: tr('Quảng cáo, TMĐT và thuế', 'Advertising, e-commerce and tax') };

  async function act(action: () => Promise<unknown>, done: string) {
    setMessage(null);
    try { await action(); setMessage({ error: false, text: done }); await cache.invalidateQueries({ queryKey: ['campaigns', campaignId] }); return true; }
    catch (caught) { setMessage({ error: true, text: caught instanceof Error ? caught.message : tr('Không thể lưu.', 'Could not save.') }); return false; }
  }
  if (detail.isLoading) return <p role="status">{tr('Đang tải…', 'Loading…')}</p>;
  if (detail.error || !detail.data) return <p role="alert">{tr('Không thể tải nội dung.', 'Unable to load content.')} <button onClick={() => void detail.refetch()}>{tr('Thử lại', 'Retry')}</button></p>;
  const item: Detail = detail.data;
  const current = item.current_version;
  const openChecks = item.checks.filter(entry => entry.result !== 'PASS');
  const time = (value: string) => new Date(value).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' });

  return <section aria-label={tr('Duyệt nội dung', 'Content review')}>
    {editing ? <form onSubmit={event => { event.preventDefault(); void act(() => api.send('POST', `${path}/versions`, { base_version_no: current.version_no, title: editing.title.trim(), body: editing.body,
        cta: editing.cta.trim(), hashtags: editing.hashtags.split(/[\s,]+/).filter(Boolean) }, detailSchema), tr('Đã lưu bản mới. Hãy chạy kiểm tra lại.', 'New version saved. Run the checks again.')).then(ok => ok && setEditing(null)); }}>
      <label className="field">{tr('Tiêu đề', 'Title')}<input value={editing.title} maxLength={200} onChange={event => setEditing({ ...editing, title: event.target.value })} required/></label>
      <label className="field">{tr('Nội dung (giữ nguyên {{AFFILIATE_LINK}})', 'Body (keep {{AFFILIATE_LINK}})')}<textarea value={editing.body} maxLength={8000} rows={8} onChange={event => setEditing({ ...editing, body: event.target.value })} required/></label>
      <label className="field">CTA<input value={editing.cta} maxLength={300} onChange={event => setEditing({ ...editing, cta: event.target.value })} required/></label>
      <label className="field">Hashtag<input value={editing.hashtags} onChange={event => setEditing({ ...editing, hashtags: event.target.value })}/></label>
      <div className="toolbar"><button className="primary" disabled={api.busy}>{tr('Lưu bản mới', 'Save new version')}</button><button type="button" onClick={() => setEditing(null)}>{tr('Huỷ', 'Cancel')}</button></div>
    </form> : <>
      <p style={{ whiteSpace: 'pre-wrap' }}>{current.body}</p><p><b>CTA:</b> {current.cta}</p>{!!current.hashtags.length && <p className="muted">#{current.hashtags.join(' #')}</p>}
      {!!current.claims.length && <ul aria-label={tr('Các khẳng định', 'Claims')}>{current.claims.map((entry, index) => <li key={index}><span className={entry.classification === 'FACT' ? 'badge badge-approved' : 'badge badge-pending'}>{entry.classification}</span> {entry.statement}</li>)}</ul>}
    </>}
    <p className="muted">{tr('Bản', 'Version')} v{current.version_no} · {current.author_kind === 'AI' ? tr('AI soạn', 'AI draft') : `${tr('Owner sửa', 'Owner edit')} (${current.author})`} · {time(current.created_at)}
      {item.versions.length > 1 && ` · ${item.versions.length} ${tr('phiên bản', 'versions')}`}</p>
    {item.decision_note && <p className="muted">{tr('Quyết định', 'Decision')}: {item.decided_by} · {item.decision_note}</p>}
    {item.versions.length > 1 && <details><summary>{tr('Lịch sử phiên bản', 'Version history')}</summary><ol>{item.versions.map(entry => <li key={entry.version_no}><b>v{entry.version_no}</b> · {entry.author_kind} · {time(entry.created_at)}<p style={{ whiteSpace: 'pre-wrap' }}>{entry.body}</p></li>)}</ol></details>}

    <div className="toolbar">
      {EDITABLE.includes(item.status) && !editing && <button onClick={() => setEditing({ title: current.title, body: current.body, cta: current.cta, hashtags: current.hashtags.join(' ') })}>{tr('Sửa', 'Edit')}</button>}
      {['DRAFT', 'CHECK_FAILED'].includes(item.status) && !editing && <button className="primary" disabled={api.busy} onClick={() => void act(() => api.send('POST', `${path}/checks/run`, {}, detailSchema), tr('Đã chạy kiểm tra.', 'Checks completed.'))}>{tr('Chạy kiểm tra', 'Run checks')}</button>}
    </div>

    {!!item.checks.length && <div className="table" aria-label={tr('Kết quả kiểm tra', 'Check results')}>{item.checks.map(entry => <div className="row" key={entry.check_name}><div><b>{labels[entry.check_name] ?? entry.check_name}</b><small>{entry.note}</small>
      {!!entry.evidence.length && <small>{entry.evidence.join(' · ')}</small>}
      {entry.result === 'NEEDS_OWNER' && item.status === 'IN_REVIEW' && <div className="actions"><label className="field">{tr('Xác nhận của Owner', 'Owner confirmation')}<input value={attest[entry.check_name] ?? ''} maxLength={1000} onChange={event => setAttest({ ...attest, [entry.check_name]: event.target.value })}/></label>
        <button disabled={api.busy || !(attest[entry.check_name] ?? '').trim()} onClick={() => void act(() => api.send('POST', `${path}/checks/${entry.check_name}/attest`, { note: (attest[entry.check_name] ?? '').trim() }, detailSchema), tr('Đã xác nhận.', 'Confirmed.'))}>{tr('Xác nhận', 'Confirm')}</button></div>}
    </div><span className={entry.result === 'PASS' ? 'badge badge-approved' : entry.result === 'FAIL' ? 'badge badge-rejected' : 'badge badge-pending'}>{entry.result === 'PASS' ? (entry.method === 'OWNER' ? tr('Owner đã xác nhận', 'Owner confirmed') : tr('Đạt', 'Pass')) : entry.result === 'FAIL' ? tr('Không đạt', 'Fail') : tr('Chờ Owner', 'Needs Owner')}</span></div>)}</div>}
    {item.status === 'CHECK_FAILED' && <p className="form-error" role="alert">{tr('Có kiểm tra không đạt. Sửa nội dung rồi chạy kiểm tra lại, hoặc từ chối.', 'Some checks failed. Edit and run the checks again, or reject.')}</p>}

    {['DRAFT', 'CHECK_FAILED', 'IN_REVIEW', 'APPROVED', 'READY_TO_PUBLISH'].includes(item.status) && <div className="toolbar">
      <label className="field">{tr('Ghi chú quyết định', 'Decision note')}<input value={note} maxLength={1000} onChange={event => setNote(event.target.value)}/></label>
      {item.status === 'IN_REVIEW' && <button className="primary" disabled={api.busy || !note.trim() || !!openChecks.length} title={openChecks.length ? tr('Còn kiểm tra chưa xử lý', 'Checks still open') : undefined}
        onClick={() => void act(() => api.send('POST', `${path}/approve`, { note: note.trim() }, detailSchema), tr('Đã duyệt.', 'Approved.')).then(ok => ok && setNote(''))}>{tr('Duyệt', 'Approve')}</button>}
      <button className="danger" disabled={api.busy || !note.trim()} onClick={() => void act(() => api.send('POST', `${path}/reject`, { note: note.trim() }, detailSchema), tr('Đã từ chối.', 'Rejected.')).then(ok => ok && setNote(''))}>{tr('Từ chối', 'Reject')}</button>
    </div>}
    {item.status === 'IN_REVIEW' && !!openChecks.length && <p className="muted">{tr('Cần xử lý trước khi duyệt', 'Resolve before approving')}: {openChecks.map(entry => labels[entry.check_name] ?? entry.check_name).join(', ')}</p>}

    {['APPROVED', 'READY_TO_PUBLISH', 'PUBLISHED'].includes(item.status) && <div className="panel"><h4>{tr('Xuất để tự đăng', 'Export to post yourself')}</h4>
      <p className="muted">{tr('App không tự đăng. Bản xuất có link thật và câu công bố của chiến dịch.', 'The app never posts. The export contains the real link and the campaign disclosure.')}</p>
      <div className="toolbar">{(['text', 'markdown'] as const).map(format => <button key={format} disabled={api.busy} onClick={() => void act(async () => setExported(await api.send('POST', `${path}/export`, { format }, exportSchema)), tr('Đã tạo bản xuất.', 'Export ready.'))}>{format === 'text' ? tr('Xuất văn bản', 'Export text') : tr('Xuất Markdown', 'Export Markdown')}</button>)}</div>
      {exported && <><label className="field">{tr('Nội dung để đăng', 'Text to post')}<textarea readOnly rows={10} value={exported.text} data-testid="export-text"/></label>
        <button onClick={() => void navigator.clipboard?.writeText(exported.text).then(() => setMessage({ error: false, text: tr('Đã sao chép.', 'Copied.') }), () => setMessage({ error: true, text: tr('Không sao chép được; hãy chọn và sao chép thủ công.', 'Copy failed; select and copy manually.') }))}>{tr('Sao chép', 'Copy')}</button></>}
    </div>}

    {['READY_TO_PUBLISH', 'PUBLISHED'].includes(item.status) && <form className="panel" onSubmit={event => { event.preventDefault(); void act(() => api.send('POST', `${path}/publish-records`, { channel: publish.channel.trim(), published_url: publish.published_url.trim(),
        published_at: new Date(publish.published_at).toISOString() }, detailSchema), tr('Đã ghi nhận bài đăng.', 'Post recorded.')).then(ok => ok && setPublish({ channel: '', published_url: '', published_at: '' })); }}>
      <h4>{tr('Ghi nhận đã đăng', 'Record the post')}</h4>
      <label className="field">{tr('Kênh', 'Channel')}<input value={publish.channel} maxLength={100} placeholder="Facebook Page" onChange={event => setPublish({ ...publish, channel: event.target.value })} required/></label>
      <label className="field">{tr('Link bài đăng', 'Post URL')}<input type="url" value={publish.published_url} maxLength={2048} onChange={event => setPublish({ ...publish, published_url: event.target.value })} required/></label>
      <label className="field">{tr('Thời điểm đăng', 'Posted at')}<input type="datetime-local" value={publish.published_at} onChange={event => setPublish({ ...publish, published_at: event.target.value })} required/></label>
      <button disabled={api.busy}>{tr('Ghi nhận', 'Record')}</button>
    </form>}
    {!!item.publish_records.length && <ul aria-label={tr('Bài đã đăng', 'Posts')}>{item.publish_records.map(entry => <li key={entry.id}>{entry.channel} · {time(entry.published_at)} · <span className="hash">{entry.published_url}</span></li>)}</ul>}
    {message && <p className={message.error ? 'form-error' : ''} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
  </section>;
}
