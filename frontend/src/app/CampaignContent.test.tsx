import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import i18n from '../i18n';
import CampaignContent from './CampaignContent';
import { useCampaignApi } from './campaignApi';

const campaignId = '00000000-0000-4000-8000-000000000002';
const linkId = '00000000-0000-4000-8000-000000000006';
const runId = '00000000-0000-4000-8000-000000000007';
const workflowId = '00000000-0000-4000-8000-000000000008';
const link = { id: linkId, program_id: '00000000-0000-4000-8000-000000000003', product_id: null, label: 'Váy maxi', original_url: 'https://s.shopee.vn/a', tracking_params: {}, final_url: 'https://s.shopee.vn/a', status: 'ACTIVE' };
const batch = { run_id: runId, workflow_id: workflowId, workflow_status: 'DRAFT', content_types: ['SOCIAL_POST'], count_per_type: 1, max_cost_usd: '0.500000', affiliate_link_id: linkId, source_count: 1, item_count: 1, created_at: '2026-11-07T00:00:00Z' };
const draft = { id: '00000000-0000-4000-8000-000000000009', batch_run_id: runId, content_type: 'SOCIAL_POST', status: 'DRAFT', created_at: '2026-11-07T00:00:00Z',
  current_version: { version_no: 1, title: 'Váy hè mát', body: 'Xem tại {{AFFILIATE_LINK}}', hashtags: ['vay'], cta: 'Mua ngay', author_kind: 'AI', created_at: '2026-11-07T00:00:00Z',
    claims: [{ classification: 'FACT', statement: 'Hoa hồng 3.68%', source_ids: ['x'] }, { classification: 'HYPOTHESIS', statement: 'Có thể hợp dân văn phòng', source_ids: [] }] } };

const paths = () => vi.mocked(fetch).mock.calls.map(([url, init]) => ({ path: String(url).replace(/^.*\/api\/v1/, ''), init }));
beforeEach(async () => {
  await i18n.changeLanguage('vi');
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const body = path.endsWith('/links') ? [link] : path.endsWith('/content-batches') ? (init?.method === 'POST' ? batch : [batch]) : path.endsWith('/content') ? [draft]
      : path.endsWith('/usage') ? { max_cost_usd: '2.000000', batch_limits_total: '0.500000', invocations: 1, calculated_cost: '0.010000', held_amount: '0.020000', by_agent: [] }
      : path === '/policies' ? [] : path.endsWith('/auto-run') ? null : [];
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderContent(status = 'ACTIVE') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useCampaignApi('owner'), { wrapper });
  return render(<QueryClientProvider client={client}><CampaignContent api={result.current} campaignId={campaignId} campaignStatus={status}/></QueryClientProvider>);
}

it('creates a batch for an active link with the chosen types and cost limit', async () => {
  renderContent();
  const select = await screen.findByLabelText('Link affiliate');
  await waitFor(() => expect(screen.getByRole('option', { name: 'Váy maxi' })).toBeInTheDocument());
  fireEvent.change(select, { target: { value: linkId } });
  fireEvent.click(screen.getByLabelText('Kịch bản video'));
  fireEvent.click(screen.getByRole('button', { name: 'Tạo lô 3 bài' }));
  expect(await screen.findByText(/Đã tạo lô nội dung/)).toBeInTheDocument();
  const post = paths().find(call => call.init?.method === 'POST');
  expect(post?.path).toBe(`/campaigns/${campaignId}/content-batches`);
  expect(JSON.parse(String(post?.init?.body))).toEqual({ affiliate_link_id: linkId, content_types: ['SOCIAL_POST', 'SHORT_CAPTION', 'VIDEO_SCRIPT'], count_per_type: 1, max_cost_usd: '0.5' });
  expect((post?.init?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
});

it('blocks batches above ten items', async () => {
  renderContent();
  await screen.findByLabelText('Link affiliate');
  for (const label of ['Kịch bản video', 'Bài đánh giá', 'Bài so sánh', 'CTA / landing']) fireEvent.click(screen.getByLabelText(label));
  fireEvent.change(screen.getByLabelText('Số bài mỗi loại'), { target: { value: '2' } });
  expect(screen.getByText('Một lô tối đa 10 bài.')).toHaveAttribute('role', 'alert');
  expect(screen.getByRole('button', { name: 'Tạo lô 12 bài' })).toBeDisabled();
});

it('shows drafts with their placeholder, claim labels, cost and the one-approval panel', async () => {
  renderContent();
  expect(await screen.findByText('Váy hè mát')).toBeInTheDocument();
  expect(screen.getByText('Xem tại {{AFFILIATE_LINK}}')).toBeInTheDocument();
  expect(screen.getByText('FACT')).toBeInTheDocument();
  expect(screen.getByText('HYPOTHESIS')).toBeInTheDocument();
  expect(await screen.findByTestId('campaign-usage')).toHaveTextContent('0.010000 USD');
  expect(await screen.findByRole('button', { name: 'Phê duyệt & chạy tự động' })).toBeInTheDocument();
  expect(paths().filter(call => call.init?.method === 'POST')).toEqual([]);
});

it('asks to activate a draft campaign before creating content', async () => {
  renderContent('DRAFT');
  expect(await screen.findByText(/Kích hoạt chiến dịch ở tab Tổng quan/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Tạo lô/ })).not.toBeInTheDocument();
});
