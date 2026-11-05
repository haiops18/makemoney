import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { z } from 'zod';
import AIResearchStages from './AIResearchStages';

const run = z.object({ id: z.string().uuid(), objective: z.string(), category: z.string().nullable(), target_market: z.string().nullable(), target_customers: z.string().nullable(), max_cost_usd: z.string(), status: z.literal('DRAFT'), opportunity_id: z.string().uuid().nullable().optional(), created_at: z.string() });
const source = z.object({ id: z.string().uuid(), source_name: z.string(), source_url: z.string().nullable(), excerpt: z.string(), verification_status: z.enum(['UNVERIFIED', 'VERIFIED', 'REJECTED']), verified_by: z.string().nullable().optional(), verification_note: z.string().nullable().optional() });
const workflow = z.object({ id: z.string().uuid(), research_run_id: z.string().uuid(), status: z.string() });
const draft = z.object({ objective: z.string().trim().min(1).max(4000), category: z.string().trim().max(150).nullable(), target_market: z.string().trim().max(200).nullable(), target_customers: z.string().trim().max(500).nullable(), max_cost_usd: z.string().regex(/^\d{1,2}(?:\.\d{1,6})?$/).refine(value => Number(value) > 0 && Number(value) <= 45) });
const evidence = z.object({ source_name: z.string().trim().min(1).max(200), source_url: z.string().url().max(2048).nullable(), excerpt: z.string().trim().min(1).max(12000) });

export default function AIResearch({ token }: { token: string }) {
  const { i18n } = useTranslation(); const vi = i18n.language.startsWith('vi'); const tr = (a: string, b: string) => vi ? a : b;
  const cache = useQueryClient(); const retry = useRef<{ signature: string; key: string } | null>(null);
  const [objective, setObjective] = useState(''); const [category, setCategory] = useState(''); const [market, setMarket] = useState(''); const [customers, setCustomers] = useState(''); const [cost, setCost] = useState('1');
  const [selected, setSelected] = useState(''); const [offset, setOffset] = useState(0); const [sourceName, setSourceName] = useState(''); const [url, setUrl] = useState(''); const [excerpt, setExcerpt] = useState('');
  const [workflowName, setWorkflowName] = useState(''); const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [success, setSuccess] = useState('');
  const base = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/research`;
  async function request(path: string, init?: RequestInit): Promise<unknown> { const response = await fetch(`${base}${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...init?.headers } }); if (!response.ok) throw new Error(`API ${response.status}`); return response.json(); }
  const runs = useQuery({ queryKey: ['ai-research', offset], enabled: !!token, queryFn: async () => z.array(run).parse(await request(`?limit=25&offset=${offset}`)) });
  const sources = useQuery({ queryKey: ['ai-research-sources', selected], enabled: !!token && !!selected, queryFn: async () => z.array(source).parse(await request(`/${selected}/sources?limit=100`)) });
  const linkedWorkflow = useQuery({ queryKey: ['ai-research-workflow', selected], enabled: !!token && !!selected, queryFn: async () => {
    const response = await fetch(`${base}/${selected}/workflow`, { headers: { Authorization: `Bearer ${token}` } });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`API ${response.status}`);
    return workflow.parse(await response.json());
  } });
  async function save(path: string, body: Record<string, unknown>, schema: z.ZodType<{ id: string }>) {
    setBusy(true); setError(''); setSuccess('');
    try { const serialized = JSON.stringify(body); const signature = `${path}:${serialized}`; if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      const result = schema.parse(await request(path, { method: 'POST', headers: { 'Idempotency-Key': retry.current.key }, body: serialized })); retry.current = null;
      if (path === '') { setSelected(result.id); setObjective(''); setCategory(''); setMarket(''); setCustomers(''); }
      else if (path.endsWith('/sources')) { setSourceName(''); setUrl(''); setExcerpt(''); }
      else if (path.endsWith('/verification')) setNotes({});
      await Promise.all([cache.invalidateQueries({ queryKey: ['ai-research'] }), cache.invalidateQueries({ queryKey: ['ai-research-sources'] }), cache.invalidateQueries({ queryKey: ['ai-research-workflow'] })]); setSuccess(path.endsWith('/workflow') ? tr('Đã tạo workflow bản nháp.', 'Draft workflow created.') : path.endsWith('/verification') ? tr('Đã ghi nhận xác minh nguồn.', 'Source decision recorded.') : tr('Đã lưu bản nháp.', 'Draft saved.'));
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể lưu.', 'Unable to save.')); } finally { setBusy(false); }
  }
  return <section><h1>{tr('Nghiên cứu AI', 'AI research')}</h1><p>{tr('Owner nhập bản nháp và nguồn. AI chỉ chạy khi từng task được phê duyệt riêng và có ngân sách; hệ thống không tự truy cập nguồn.', 'The Owner enters drafts and sources. AI runs only after each task is separately approved and budgeted; sources are never fetched automatically.')}</p>
    {!token ? <p>{tr('Vui lòng đăng nhập Owner.', 'Sign in as Owner.')}</p> : <>
      <form className="panel" onSubmit={event => { event.preventDefault(); const parsed = draft.safeParse({ objective, category: category || null, target_market: market || null, target_customers: customers || null, max_cost_usd: cost }); if (!parsed.success) { setError(tr('Kiểm tra mục tiêu và ngân sách.', 'Check objective and budget.')); return; } void save('', parsed.data, run); }}>
        <h2>{tr('Tạo yêu cầu nghiên cứu', 'Create research request')}</h2><label className="field">{tr('Mục tiêu nghiên cứu', 'Research objective')}<textarea value={objective} onChange={event => setObjective(event.target.value)} maxLength={4000} required/></label>
        <label className="field">{tr('Danh mục', 'Category')}<input value={category} onChange={event => setCategory(event.target.value)} maxLength={150}/></label><label className="field">{tr('Thị trường mục tiêu', 'Target market')}<input value={market} onChange={event => setMarket(event.target.value)} maxLength={200}/></label>
        <label className="field">{tr('Khách hàng mục tiêu', 'Target customers')}<input value={customers} onChange={event => setCustomers(event.target.value)} maxLength={500}/></label><label className="field">{tr('Chi phí tối đa (USD)', 'Maximum cost (USD)')}<input type="number" min="0.000001" max="45" step="0.000001" value={cost} onChange={event => setCost(event.target.value)} required/></label><button disabled={busy}>{tr('Tạo bản nháp', 'Create draft')}</button>
      </form>{error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}{runs.isLoading && <p>{tr('Đang tải…', 'Loading…')}</p>}{runs.error && <p role="alert">{tr('Không thể tải yêu cầu.', 'Unable to load requests.')}</p>}
      {runs.data?.length === 0 && <p>{tr('Chưa có yêu cầu nghiên cứu.', 'No research requests.')}</p>}{runs.data?.map(item => <article className="panel" key={item.id}><button type="button" onClick={() => setSelected(item.id)}>{item.objective}</button><p>{item.status} · {item.max_cost_usd} USD · {new Date(item.created_at).toLocaleString(vi ? 'vi-VN' : 'en-US', { timeZone: 'Asia/Ho_Chi_Minh' })}</p></article>)}
      <div className="toolbar"><button disabled={!offset || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>{tr('Trước', 'Previous')}</button><button disabled={!runs.data || runs.data.length < 25 || busy} onClick={() => setOffset(offset + 25)}>{tr('Tiếp', 'Next')}</button></div>
      {selected && <section className="panel"><h2>{tr('Nguồn Owner nhập', 'Owner-entered sources')}</h2><p>{tr('Nguồn không được tự động truy cập. Chỉ nguồn Owner đã xác minh mới được dùng làm căn cứ cho FACT; nguồn bị từ chối không gửi cho AI.', 'Sources are never fetched automatically. Only Owner-verified sources can support a FACT; rejected sources are not sent to AI.')}</p><form onSubmit={event => { event.preventDefault(); const parsed = evidence.safeParse({ source_name: sourceName, source_url: url || null, excerpt }); if (!parsed.success) { setError(tr('Kiểm tra nguồn và trích đoạn.', 'Check source and excerpt.')); return; } void save(`/${selected}/sources`, parsed.data, source); }}>
        <label className="field">{tr('Tên nguồn', 'Source name')}<input value={sourceName} onChange={event => setSourceName(event.target.value)} maxLength={200} required/></label><label className="field">URL<input value={url} onChange={event => setUrl(event.target.value)} maxLength={2048}/></label><label className="field">{tr('Trích đoạn', 'Excerpt')}<textarea value={excerpt} onChange={event => setExcerpt(event.target.value)} maxLength={12000} required/></label><button disabled={busy}>{tr('Thêm nguồn', 'Add source')}</button>
      </form>{sources.isLoading && <p>{tr('Đang tải…', 'Loading…')}</p>}{sources.error && <p role="alert">{tr('Không thể tải nguồn.', 'Unable to load sources.')}</p>}{sources.data?.length === 0 && <p>{tr('Chưa có nguồn.', 'No sources.')}</p>}{sources.data?.map(item => <article key={item.id}><b>{item.source_name} · {item.verification_status}</b><p>{item.source_url ?? 'UNKNOWN'}</p><p>{item.excerpt}</p>
        {item.verification_status === 'UNVERIFIED' ? <div className="toolbar"><label className="field">{tr('Ghi chú xác minh', 'Verification note')}<input value={notes[item.id] ?? ''} onChange={event => setNotes({ ...notes, [item.id]: event.target.value })} maxLength={1000}/></label>
          {(['VERIFIED', 'REJECTED'] as const).map(status => <button key={status} type="button" disabled={busy || !(notes[item.id] ?? '').trim()} onClick={() => { if (window.confirm(tr('Quyết định này không thể thay đổi. Tiếp tục?', 'This decision is final. Continue?'))) void save(`/${selected}/sources/${item.id}/verification`, { status, note: (notes[item.id] ?? '').trim() }, source); }}>{status === 'VERIFIED' ? tr('Xác minh', 'Verify') : tr('Từ chối', 'Reject')}</button>)}</div>
          : <p>{item.verified_by} · {item.verification_note}</p>}</article>)}
      <h3>{tr('Workflow nghiên cứu', 'Research workflow')}</h3><p>{tr('Task kiểm tra nội bộ chỉ kiểm tra thông tin. Các giai đoạn AI được thêm riêng và mỗi giai đoạn cần phê duyệt riêng.', 'The internal validation task checks fields only. AI stages are added separately and each needs its own approval.')}</p>
      {linkedWorkflow.isLoading && <p>{tr('Đang tải workflow…', 'Loading workflow…')}</p>}{linkedWorkflow.error && <p role="alert">{tr('Không thể tải workflow.', 'Unable to load workflow.')}</p>}
      {linkedWorkflow.data ? <p>{linkedWorkflow.data.status} · <Link to="/workflows">{tr('Mở Workflow', 'Open workflows')}</Link></p> : linkedWorkflow.data === null && <form onSubmit={event => { event.preventDefault(); const name = z.string().trim().min(1).max(200).safeParse(workflowName); if (!name.success) { setError(tr('Nhập tên workflow.', 'Enter a workflow name.')); return; } void save(`/${selected}/workflow`, { name: name.data }, workflow); }}><label className="field">{tr('Tên workflow nghiên cứu', 'Research workflow name')}<input value={workflowName} onChange={event => setWorkflowName(event.target.value)} maxLength={200} required/></label><button disabled={busy}>{tr('Tạo workflow nghiên cứu', 'Create research workflow')}</button></form>}
      {linkedWorkflow.data && <AIResearchStages token={token} runId={selected} workflowStatus={linkedWorkflow.data.status}/>}
      </section>}
    </>}
  </section>;
}
