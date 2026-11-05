import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import AIAgentProfiles from './AIAgentProfiles';

const agentId = '00000000-0000-4000-8000-000000000001';
const providerId = '00000000-0000-4000-8000-000000000002';
const profileId = '00000000-0000-4000-8000-000000000003';
beforeEach(async () => {
  await i18n.changeLanguage('vi');
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'PUT') return { ok: true, json: async () => ({ id: profileId, agent_id: agentId, ...JSON.parse(String(init.body)), temperature: null }) } as Response;
    const items = url.endsWith('/agents') ? [{ id: agentId, name: 'Research', role: 'research' }] : url.includes('/ai/providers') ? [{ id: providerId, name: 'Provider' }] : [];
    return { ok: true, json: async () => items } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('configures an agent with a provider and verified idempotent response', async () => {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AIAgentProfiles token="owner"/></QueryClientProvider>);
  await screen.findByRole('option', { name: 'Research · research' });
  fireEvent.change(screen.getByLabelText('Agent'), { target: { value: agentId } });
  fireEvent.change(screen.getByLabelText('Provider'), { target: { value: providerId } });
  fireEvent.change(screen.getByLabelText('Model ID của agent'), { target: { value: 'model-test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình agent' }));
  await waitFor(() => expect(screen.getByText('Đã lưu cấu hình agent.')).toBeInTheDocument());
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PUT');
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
  expect(JSON.parse(String(call?.[1]?.body)).enabled).toBe(false);
});
