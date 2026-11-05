import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import AIConsent from './AIConsent';

const controlId = '00000000-0000-4000-8000-000000000001';
const policyId = '00000000-0000-4000-8000-000000000002';
const approvalId = '00000000-0000-4000-8000-000000000003';
const action = { policy_id: policyId, action_type: 'AI_CONTROL_ENABLE', action_payload: { control_version: 1, enabled: true }, resource_type: 'ai_execution_control', resource_id: controlId, scope: 'ONCE' };
beforeEach(async () => {
  await i18n.changeLanguage('vi');
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const data = url.includes('/enable-action') ? { action, action_hash: 'exact-hash' }
      : url.endsWith('/ai/control') ? { id: controlId, enabled: false, version: 1, execution_available: false }
      : url.endsWith('/policies') ? [{ id: policyId, enabled: true, rules_json: { allowed_action_types: ['AI_CONTROL_ENABLE'], ai_inference_allowed: true, external_execution: false } }]
      : init?.method === 'POST' ? { id: approvalId, status: 'PENDING', action_hash: 'exact-hash', resource_id: controlId }
      : { items: [] };
    return { ok: true, json: async () => data } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('requires approval before enabling and requests the server-prepared action', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AIConsent token="owner"/></QueryClientProvider>);
  expect(await screen.findByText(/Quyền Owner: Đã tắt/)).toHaveTextContent('Thực thi AI: Chưa khả dụng');
  expect(screen.getByRole('button', { name: 'Bật quyền AI' })).toBeDisabled();
  const request = screen.getByRole('button', { name: 'Yêu cầu phê duyệt quyền AI' });
  await waitFor(() => expect(request).toBeEnabled());
  fireEvent.click(request);
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith('/approvals') && init?.method === 'POST')).toBe(true));
  const call = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith('/approvals') && init?.method === 'POST');
  expect(JSON.parse(String(call?.[1]?.body)).action_payload.control_version).toBe(1);
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
});
