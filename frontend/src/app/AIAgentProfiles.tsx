import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

const agent = z.object({ id: z.string().uuid(), name: z.string(), role: z.string() });
const provider = z.object({ id: z.string().uuid(), name: z.string() });
const profile = z.object({ id: z.string().uuid(), agent_id: z.string().uuid(), provider_id: z.string().uuid(), model_id: z.string(), max_output_tokens: z.number(), temperature: z.string().nullable(), timeout_seconds: z.number(), max_cost_usd: z.string(), enabled: z.boolean() });
const input = z.object({ provider_id: z.string().uuid(), model_id: z.string().trim().min(1).max(200), max_output_tokens: z.number().int().min(1).max(100000), temperature: z.string().regex(/^(?:0(?:\.\d{1,2})?|1(?:\.\d{1,2})?|2(?:\.0{1,2})?)$/).nullable(), timeout_seconds: z.number().int().min(1).max(300), max_cost_usd: z.string().regex(/^\d{1,2}(?:\.\d{1,6})?$/).refine(value => Number(value) > 0 && Number(value) <= 45), enabled: z.boolean() });

export default function AIAgentProfiles({ token }: { token: string }) {
  const { i18n } = useTranslation(); const vi = i18n.language.startsWith('vi'); const tr = (a: string, b: string) => vi ? a : b;
  const cache = useQueryClient(); const retry = useRef<{ signature: string; key: string } | null>(null);
  const [agentId, setAgentId] = useState(''); const [providerId, setProviderId] = useState(''); const [model, setModel] = useState('');
  const [tokens, setTokens] = useState(1000); const [temperature, setTemperature] = useState(''); const [timeout, setTimeout] = useState(60); const [cost, setCost] = useState('1'); const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [success, setSuccess] = useState('');
  const base = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1`;
  async function get(path: string) { const response = await fetch(`${base}${path}`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error(`API ${response.status}`); return response.json(); }
  const agents = useQuery({ queryKey: ['ai-profile-agents'], enabled: !!token, queryFn: async () => z.array(agent).parse(await get('/agents')) });
  const providers = useQuery({ queryKey: ['ai-profile-providers'], enabled: !!token, queryFn: async () => z.array(provider).parse(await get('/ai/providers?limit=100')) });
  const profiles = useQuery({ queryKey: ['ai-agent-profiles'], enabled: !!token, queryFn: async () => z.array(profile).parse(await get('/ai/agent-profiles')) });
  async function save() {
    setError(''); setSuccess('');
    const result = input.safeParse({ provider_id: providerId, model_id: model, max_output_tokens: tokens, temperature: temperature || null, timeout_seconds: timeout, max_cost_usd: cost, enabled });
    if (!agentId || !result.success) { setError(tr('Kiểm tra agent và giới hạn cấu hình.', 'Check agent and configuration limits.')); return; }
    setBusy(true);
    try {
      const body = JSON.stringify(result.data); const signature = `${agentId}:${body}`;
      if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
      const response = await fetch(`${base}/ai/agent-profiles/${agentId}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': retry.current.key }, body });
      if (!response.ok) throw new Error(`API ${response.status}`);
      profile.parse(await response.json()); retry.current = null;
      await cache.invalidateQueries({ queryKey: ['ai-agent-profiles'] }); setSuccess(tr('Đã lưu cấu hình agent.', 'Agent configuration saved.'));
    } catch (e) { setError(e instanceof Error ? e.message : tr('Không thể lưu.', 'Unable to save.')); }
    finally { setBusy(false); }
  }
  function chooseAgent(id: string) { setAgentId(id); const current = profiles.data?.find(item => item.agent_id === id); if (current) { setProviderId(current.provider_id); setModel(current.model_id); setTokens(current.max_output_tokens); setTemperature(current.temperature ?? ''); setTimeout(current.timeout_seconds); setCost(current.max_cost_usd); setEnabled(current.enabled); } else { setProviderId(''); setModel(''); setTokens(1000); setTemperature(''); setTimeout(60); setCost('1'); setEnabled(false); } }
  if (!token) return null;
  return <section className="panel"><h2>{tr('Model theo agent', 'Models by agent')}</h2><p>{tr('Lưu cấu hình không chạy AI. AI chỉ chạy khi quyền AI toàn cục đang bật và từng task được phê duyệt riêng.', 'Saving a configuration does not run AI. AI runs only while global AI consent is on and each task has its own approval.')}</p>
    {(agents.isLoading || providers.isLoading || profiles.isLoading) && <p>{tr('Đang tải…', 'Loading…')}</p>}
    {(agents.error || providers.error || profiles.error) && <p role="alert">{tr('Không thể tải cấu hình.', 'Unable to load configuration.')}</p>}
    <form onSubmit={event => { event.preventDefault(); void save(); }}>
      <label className="field">Agent<select value={agentId} onChange={event => chooseAgent(event.target.value)} required><option value="">{tr('Chọn agent', 'Select agent')}</option>{agents.data?.map(item => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}</select></label>
      <label className="field">Provider<select value={providerId} onChange={event => setProviderId(event.target.value)} required><option value="">{tr('Chọn provider', 'Select provider')}</option>{providers.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="field">{tr('Model ID của agent', 'Agent model ID')}<input value={model} onChange={event => setModel(event.target.value)} maxLength={200} required/></label>
      <label className="field">{tr('Token đầu ra tối đa', 'Maximum output tokens')}<input type="number" min="1" max="100000" value={tokens} onChange={event => setTokens(Number(event.target.value))} required/></label>
      <label className="field">Temperature<input type="number" min="0" max="2" step="0.01" value={temperature} onChange={event => setTemperature(event.target.value)}/></label>
      <label className="field">{tr('Timeout (giây)', 'Timeout (seconds)')}<input type="number" min="1" max="300" value={timeout} onChange={event => setTimeout(Number(event.target.value))} required/></label>
      <label className="field">{tr('Chi phí tối đa mỗi lần (USD)', 'Maximum cost per run (USD)')}<input type="number" min="0.000001" max="45" step="0.000001" value={cost} onChange={event => setCost(event.target.value)} required/></label>
      <label className="field"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)}/>{tr('Bật cấu hình agent', 'Enable agent configuration')}</label>
      <button disabled={busy}>{tr('Lưu cấu hình agent', 'Save agent configuration')}</button>
    </form>{error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}</section>;
}
