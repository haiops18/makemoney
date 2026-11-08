import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import Integrations from './Integrations';

const id = '00000000-0000-4000-8000-000000000031';
const row = { id, kind: 'FACEBOOK_PAGE', label: 'Trang váy', purpose: 'posting', config: { page_id: '1234567890', graph_version: 'v26.0' }, has_secret: true, enabled: true, check_costs: false,
  last_checked_at: null, last_check_status: null, last_check_detail: null };
let rows: Record<string, unknown>[];
const calls = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method).map(([url, init]) => ({ path: String(url).replace(/^.*\/api\/v1/, ''), method: init?.method, body: JSON.parse(String(init?.body)) }));

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  rows = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    let body: unknown = rows;
    if (init?.method === 'POST' && path === '/integrations') { rows = [row]; body = row; }
    else if (path.endsWith('/test')) { rows = [{ ...row, last_check_status: 'OK', last_check_detail: 'Page: Váy hè', last_checked_at: '2026-11-08T13:00:00Z' }]; body = rows[0]; }
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><Integrations token="owner"/></QueryClientProvider>);
}

it('saves a Facebook Page once, clears the token field and checks the connection', async () => {
  renderPage();
  expect(await screen.findByText('Chưa có kết nối nào.')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Loại'), { target: { value: 'FACEBOOK_PAGE' } });
  fireEvent.change(screen.getByLabelText('Tên gợi nhớ (tuỳ chọn)'), { target: { value: 'Trang váy' } });
  fireEvent.change(screen.getByLabelText('Page ID (dạng số)'), { target: { value: '1234567890' } });
  const secret = screen.getByLabelText('Page access token');
  expect(secret).toHaveAttribute('type', 'password');
  fireEvent.change(secret, { target: { value: 'EAAG-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu kết nối' }));
  expect(await screen.findByText(/Token được mã hóa/)).toBeInTheDocument();
  expect(secret).toHaveValue('');
  expect(calls()[0]).toEqual({ path: '/integrations', method: 'POST', body: { kind: 'FACEBOOK_PAGE', label: 'Trang váy', secret: 'EAAG-secret', config: { page_id: '1234567890' } } });
  expect(await screen.findByText(/Token đã lưu \(đã mã hóa\)/)).toBeInTheDocument();
  expect(screen.queryByText(/EAAG-secret/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra kết nối' }));
  await waitFor(() => expect(screen.getByText(/Kết nối tốt — Page: Váy hè/)).toBeInTheDocument());
});

it('asks before a search check that uses a paid query', async () => {
  rows = [{ ...row, kind: 'SEARCH_TAVILY', label: 'Tavily', purpose: 'search', config: {}, check_costs: true }];
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Kiểm tra kết nối' }));
  expect(confirm).toHaveBeenCalledWith('Kiểm tra sẽ dùng 1 lượt tìm kiếm có tính phí. Tiếp tục?');
  expect(calls()).toEqual([]);
});
