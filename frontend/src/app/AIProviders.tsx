import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import AIAgentProfiles from './AIAgentProfiles';
import AIModelPrices from './AIModelPrices';

const provider = z.object({ id: z.string().uuid(), name: z.string(), kind: z.string(), base_url: z.string().nullable(), default_model: z.string(), enabled: z.boolean(), archived: z.boolean(), is_default: z.boolean(), has_api_key: z.boolean() });
const createSchema = z.object({ name: z.string().trim().min(1).max(150), kind: z.enum(['OPENAI', 'GEMINI', 'ANTHROPIC', 'OPENAI_COMPATIBLE']), default_model: z.string().trim().min(1).max(200), base_url: z.string().url().startsWith('https://').max(2048).nullable(), api_key: z.string().min(1).max(4096).optional() });
type Provider = z.infer<typeof provider>;

export default function AIProviders({ token }: { token: string }) {
  const { i18n } = useTranslation();
  const vi = i18n.language.startsWith('vi');
  const tr = (vn: string, en: string) => vi ? vn : en;
  const cache = useQueryClient();
  const secret = useRef<HTMLInputElement>(null);
  const pendingKey = useRef<{ digest: string; key: string } | null>(null);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'OPENAI' | 'GEMINI' | 'ANTHROPIC' | 'OPENAI_COMPATIBLE'>('OPENAI');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [editing, setEditing] = useState<Provider | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [offset, setOffset] = useState(0);
  const [pricingProvider, setPricingProvider] = useState<Provider | null>(null);
  const base = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/providers`;
  const query = useQuery({ queryKey: ['ai-providers', offset], enabled: !!token, queryFn: async () => {
    const response = await fetch(`${base}?limit=25&offset=${offset}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return z.array(provider).parse(await response.json());
  } });
  async function mutate(path: string, method: 'POST' | 'PATCH', body: Record<string, unknown>) {
    setBusy(true); setError(''); setSuccess('');
    try {
      const serialized = JSON.stringify(body);
      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${method}:${path}:${serialized}`));
      const digest = Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('');
      if (pendingKey.current?.digest !== digest) pendingKey.current = { digest, key: crypto.randomUUID() };
      const response = await fetch(`${base}${path}`, { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': pendingKey.current.key }, body: serialized });
      if (!response.ok) throw new Error(`API ${response.status}`);
      provider.parse(await response.json());
      pendingKey.current = null;
      if (secret.current) secret.current.value = '';
      setName(''); setModel(''); setBaseUrl(''); setEditing(null);
      await Promise.all([cache.invalidateQueries({ queryKey: ['ai-providers'] }), cache.invalidateQueries({ queryKey: ['ai-profile-providers'] })]);
      setSuccess(tr('Đã lưu cấu hình.', 'Configuration saved.'));
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể lưu.', 'Unable to save.')); }
    finally { setBusy(false); }
  }
  function edit(item: Provider) { setEditing(item); setName(item.name); setKind(item.kind as typeof kind); setModel(item.default_model); setBaseUrl(item.base_url ?? ''); if (secret.current) secret.current.value = ''; }
  return <section className="panel"><h2>{tr('Quản lý AI provider', 'AI providers')}</h2>
    <p>{tr('Cấu hình không kích hoạt AI trả phí. Chạy nghiên cứu và kiểm tra kết nối chưa khả dụng.', 'Configuration does not activate paid AI. Research execution and connection tests are unavailable.')}</p>
    {!token && <p>{tr('Đăng nhập Owner để quản lý.', 'Sign in as Owner to manage providers.')}</p>}
    {token && <><form onSubmit={event => { event.preventDefault(); const input = createSchema.safeParse({ name, kind, default_model: model, base_url: baseUrl.trim() || null, ...(secret.current?.value ? { api_key: secret.current.value } : {}) }); if (!input.success) { setError(tr('Kiểm tra tên, model, URL và khóa.', 'Check name, model, URL and key.')); return; } const { kind: providerKind, ...rest } = input.data; void mutate(editing ? `/${editing.id}` : '', editing ? 'PATCH' : 'POST', editing ? rest : { ...rest, kind: providerKind }); }}>
      <h3>{editing ? tr('Sửa provider', 'Edit provider') : tr('Thêm provider', 'Add provider')}</h3>
      <label className="field">{tr('Tên', 'Name')}<input value={name} onChange={event => setName(event.target.value)} required maxLength={150}/></label>
      <label className="field">Provider<select value={kind} disabled={!!editing} onChange={event => setKind(event.target.value as typeof kind)}><option>OPENAI</option><option>GEMINI</option><option>ANTHROPIC</option><option>OPENAI_COMPATIBLE</option></select></label>
      <label className="field">Model ID<input value={model} onChange={event => setModel(event.target.value)} required maxLength={200}/></label>
      <label className="field">Base URL<input value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://" maxLength={2048}/></label>
      <label className="field">API key<input type="password" autoComplete="new-password" ref={secret} maxLength={4096}/></label>
      <button disabled={busy}>{tr('Lưu', 'Save')}</button>{editing && <button type="button" onClick={() => { setEditing(null); setName(''); setModel(''); setBaseUrl(''); if (secret.current) secret.current.value = ''; }}>{tr('Hủy', 'Cancel')}</button>}
    </form>{error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
    {query.isLoading && <p>{tr('Đang tải…', 'Loading…')}</p>}{query.error && <p role="alert">{tr('Không thể tải provider.', 'Unable to load providers.')}</p>}
    {query.data?.length === 0 && <p>{tr('Chưa có provider.', 'No providers configured.')}</p>}
    {query.data?.map(item => <article className="panel" key={item.id}><b>{item.name}</b><p>{item.kind} · {item.default_model} · {item.is_default ? tr('Mặc định', 'Default') : ''} · {item.has_api_key ? tr('Đã lưu khóa', 'Key configured') : tr('Chưa có khóa', 'No key')}</p>
      <div className="toolbar"><button disabled={busy} onClick={() => edit(item)}>{tr('Sửa', 'Edit')}</button><button disabled={busy} onClick={() => void mutate(`/${item.id}`, 'PATCH', { enabled: !item.enabled })}>{item.enabled ? tr('Tắt cấu hình', 'Disable configuration') : tr('Bật cấu hình', 'Enable configuration')}</button>
      <button disabled={busy || item.is_default} onClick={() => void mutate(`/${item.id}/default`, 'POST', {})}>{tr('Chọn mặc định', 'Set default')}</button>
      <button disabled={busy} onClick={() => setPricingProvider(pricingProvider?.id === item.id ? null : item)}>{tr('Cấu hình giá', 'Configure prices')}</button>
      <button disabled={busy || !item.has_api_key} onClick={() => { if (window.confirm(tr('Thu hồi khóa đã lưu?', 'Revoke the stored key?'))) void mutate(`/${item.id}`, 'PATCH', { revoke_api_key: true }); }}>{tr('Thu hồi khóa', 'Revoke key')}</button>
      <button disabled={busy} onClick={() => { if (window.confirm(tr('Lưu trữ provider này?', 'Archive this provider?'))) void mutate(`/${item.id}/archive`, 'POST', {}); }}>{tr('Lưu trữ', 'Archive')}</button></div></article>)}
    <div className="toolbar"><button disabled={!offset || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>{tr('Trước', 'Previous')}</button><button disabled={!query.data || query.data.length < 25 || busy} onClick={() => setOffset(offset + 25)}>{tr('Tiếp', 'Next')}</button></div></>}
    {token && pricingProvider && <AIModelPrices key={pricingProvider.id} token={token} providerId={pricingProvider.id} defaultModel={pricingProvider.default_model}/>}
    <AIAgentProfiles token={token}/>
  </section>;
}
