import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import Campaigns from './Campaigns';

const opportunityId = '00000000-0000-4000-8000-000000000001';
const campaignId = '00000000-0000-4000-8000-000000000002';
const programId = '00000000-0000-4000-8000-000000000003';
const sourceId = '00000000-0000-4000-8000-000000000004';
const campaign = { id: campaignId, opportunity_id: opportunityId, name: 'Thời trang nữ', business_model: 'AFFILIATE', niche: 'Váy', target_audience: null, goal: null, language: 'vi', disclosure_text: null, max_cost_usd: '2.000000', status: 'DRAFT', version: 1, created_at: '2026-11-07T00:00:00Z' };
const program = { id: programId, network: 'SHOPEE', name: 'Shopee Affiliate', join_url: null, link_hosts: ['s.shopee.vn'], tracking_param_keys: ['sub_id'],
  terms: [{ id: '00000000-0000-4000-8000-000000000005', term: 'COMMISSION_RATE', value_text: '3.68%', value_numeric: '3.680000', unit: 'PERCENT', source_id: sourceId, evidence_status: 'UNVERIFIED' }] };
const source = { id: sourceId, source_name: 'GHN', source_url: 'https://ghn.vn/x', excerpt: '3.68%', captured_at: '2026-11-06T00:00:00Z', verification_status: 'UNVERIFIED' };
const link = { id: '00000000-0000-4000-8000-000000000006', program_id: programId, product_id: null, label: 'Váy', original_url: 'https://s.shopee.vn/a', tracking_params: { sub_id: 'r1' }, final_url: 'https://s.shopee.vn/a?sub_id=r1', status: 'ACTIVE' };

type Reply = { status?: number; body: unknown };
let routes: (url: string, init?: RequestInit) => Reply | undefined;
const calls = () => vi.mocked(fetch).mock.calls.map(([url, init]) => ({ url: String(url).replace(/^.*\/api\/v1/, ''), init }));
const posts = () => calls().filter(call => call.init?.method === 'POST' || call.init?.method === 'PATCH');

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  routes = () => undefined;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const custom = routes(path, init);
    const reply: Reply = custom ?? (path.startsWith('/opportunities') ? { body: { items: [{ id: opportunityId, title: 'Shopee thời trang nữ', business_model: 'AFFILIATE', score: 80 }] } }
      : path === '/campaigns' && init?.method === 'POST' ? { body: campaign }
      : path.startsWith('/campaigns?') ? { body: [campaign] }
      : path.endsWith('/programs') ? { body: [program] }
      : path.endsWith('/sources') ? { body: [source] }
      : path.endsWith('/links') ? { body: [link] }
      : { body: [] });
    return { ok: (reply.status ?? 200) < 400, status: reply.status ?? 200, json: async () => reply.body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const renderPage = (token = 'owner') => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Campaigns token={token}/></QueryClientProvider>);

it('requires sign in and makes no request', () => {
  renderPage('');
  expect(screen.getByText('Vui lòng đăng nhập Owner.')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it('creates a campaign from an evaluated opportunity with an idempotency key', async () => {
  renderPage();
  const select = await screen.findByLabelText('Cơ hội đã đánh giá');
  await waitFor(() => expect(within(select).getByText(/Shopee thời trang nữ/)).toBeInTheDocument());
  expect(calls().some(call => call.url.includes('status_filter=EVALUATED'))).toBe(true);
  fireEvent.change(select, { target: { value: opportunityId } });
  fireEvent.change(screen.getByLabelText('Tên chiến dịch'), { target: { value: 'Thời trang nữ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo chiến dịch' }));
  expect(await screen.findByText('Đã tạo chiến dịch.')).toBeInTheDocument();
  const [created] = posts();
  expect(created.url).toBe('/campaigns');
  expect(JSON.parse(String(created.init?.body))).toMatchObject({ opportunity_id: opportunityId, name: 'Thời trang nữ', max_cost_usd: '2', niche: null });
  expect((created.init?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
  expect(screen.getByRole('tab', { name: 'Tổng quan', selected: true })).toBeInTheDocument();
});

it('keeps the same idempotency key when a failed save is retried', async () => {
  let attempts = 0;
  routes = (path, init) => path === '/campaigns' && init?.method === 'POST' && attempts++ === 0 ? { status: 503, body: { detail: 'Database unavailable' } } : undefined;
  renderPage();
  const select = await screen.findByLabelText('Cơ hội đã đánh giá');
  await waitFor(() => expect(within(select).getByText(/Shopee/)).toBeInTheDocument());
  fireEvent.change(select, { target: { value: opportunityId } });
  fireEvent.change(screen.getByLabelText('Tên chiến dịch'), { target: { value: 'Retry' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo chiến dịch' }));
  expect(await screen.findByText('Database unavailable')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo chiến dịch' }));
  expect(await screen.findByText('Đã tạo chiến dịch.')).toBeInTheDocument();
  const keys = posts().map(call => (call.init?.headers as Record<string, string>)['Idempotency-Key']);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

it('shows term evidence status and saves a disclosure only when the Owner enters one', async () => {
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Mở' }));
  expect(screen.getByText(/Không có câu mặc định/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('tab', { name: 'Chương trình & điều khoản' }));
  expect(await screen.findByText('3.68% · 3.680000 PERCENT')).toBeInTheDocument();
  expect(screen.getAllByText('Nguồn chưa xác minh').length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole('tab', { name: 'Link affiliate' }));
  expect(await screen.findByText('https://s.shopee.vn/a?sub_id=r1')).toBeInTheDocument();
  expect(posts()).toEqual([]);
});

it('verifies a source only with a note and an explicit confirmation', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  routes = (path, init) => path.endsWith('/verification') && init?.method === 'POST' ? { body: { ...source, verification_status: 'VERIFIED', verified_by: 'owner', verification_note: 'ok' } } : undefined;
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Mở' }));
  fireEvent.click(screen.getByRole('tab', { name: 'Nguồn' }));
  const verify = await screen.findByRole('button', { name: 'Xác minh' });
  expect(verify).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Ghi chú xác minh'), { target: { value: 'Đã đối chiếu trang GHN' } });
  fireEvent.click(verify);
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(confirm).toHaveBeenCalled();
  expect(posts()[0].url).toBe(`/campaigns/${campaignId}/sources/${sourceId}/verification`);
  expect(JSON.parse(String(posts()[0].init?.body))).toEqual({ status: 'VERIFIED', note: 'Đã đối chiếu trang GHN' });
});

it('shows a load error with a retry button', async () => {
  routes = path => path.startsWith('/campaigns?') ? { status: 500, body: {} } : undefined;
  renderPage();
  expect(await screen.findByText(/Không thể tải chiến dịch/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument();
});
