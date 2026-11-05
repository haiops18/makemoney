import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import AIProviders from './AIProviders';

const item = { id: '00000000-0000-4000-8000-000000000001', name: 'Test', kind: 'OPENAI', base_url: null, default_model: 'model', enabled: false, archived: false, is_default: false, has_api_key: true };
const renderPage = (token = 'owner-session') => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AIProviders token={token}/></QueryClientProvider>);

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  vi.stubGlobal('crypto', { randomUUID: () => 'test-idempotency', subtle: { digest: async () => new Uint8Array(32).buffer } });
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => init?.method === 'POST' ? item : [] }) as Response));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('requires an Owner session without querying the API', () => {
  renderPage('');
  expect(screen.getByText('Đăng nhập Owner để quản lý.')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it('sends a credential only to the backend, verifies the response and clears the input', async () => {
  renderPage();
  fireEvent.change(screen.getByLabelText('Tên'), { target: { value: 'Test' } });
  fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: 'model' } });
  fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'test-key-only' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Đã lưu cấu hình.'));
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST');
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBe('test-idempotency');
  expect(screen.getByLabelText('API key')).toHaveValue('');
  expect(document.body.textContent).not.toContain('test-key-only');
});

it('displays API errors and English labels', async () => {
  await i18n.changeLanguage('en');
  vi.mocked(fetch).mockResolvedValue({ ok: false, status: 503 } as Response);
  renderPage();
  expect(screen.getByText('Configuration does not activate paid AI by itself. Only OpenAI, Anthropic and Gemini on their official endpoints are supported; custom URLs and OPENAI_COMPATIBLE are blocked from execution. Connection tests require global AI consent.')).toBeInTheDocument();
  expect(await screen.findByText('Unable to load providers.')).toBeInTheDocument();
});

it('runs a confirmed connection test only for verified adapters and shows the outcome', async () => {
  const verified = { ...item, adapter_verified: true, last_check_status: null };
  const custom = { ...item, id: '00000000-0000-4000-8000-000000000002', name: 'Compat', kind: 'OPENAI_COMPATIBLE', adapter_verified: false };
  vi.mocked(fetch).mockImplementation(async (url: string | URL | Request, init?: RequestInit) => ({ ok: true, status: 200, json: async () => String(url).endsWith('/connection-test') ? { provider_id: item.id, status: 'OK', model_listed: false, checked_at: '2026-11-05T00:00:00Z' } : init?.method ? item : [verified, custom] }) as Response);
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  renderPage();
  const buttons = await screen.findAllByRole('button', { name: 'Kiểm tra kết nối' });
  expect(buttons[1]).toBeDisabled();
  expect(screen.getByText(/Không hỗ trợ thực thi/)).toBeInTheDocument();
  fireEvent.click(buttons[0]);
  expect(await screen.findByText('Kết quả kiểm tra: OK · model mặc định không có trong danh sách')).toBeInTheDocument();
  const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/connection-test'));
  expect(call?.[1]?.method).toBe('POST');
  expect(call?.[1]?.body).toBeUndefined();
});
