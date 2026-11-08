import { cleanup, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import Proposals from './Proposals';
import { AccesstradeImport } from './CampaignAutopilot';
import { useCampaignApi } from './campaignApi';

const campaignId = '00000000-0000-4000-8000-000000000051';
const contentId = '00000000-0000-4000-8000-000000000052';
const proposal = { content_id: contentId, campaign_id: campaignId, campaign_name: 'Váy hè', content_type: 'SOCIAL_POST', title: 'Váy maxi', body: 'Xem tại {{AFFILIATE_LINK}}',
  hashtags: ['vay'], cta: 'Mua ngay', link_label: 'Váy', ready: true, open_checks: [], created_at: '2026-11-08T13:00:00Z' };
let proposals: unknown[];
const posts = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST').map(([url, init]) => ({ path: String(url).replace(/^.*\/api\/v1/, ''), body: JSON.parse(String(init?.body)) }));

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  proposals = [proposal, { ...proposal, content_id: '00000000-0000-4000-8000-000000000053', title: 'Áo', ready: false, open_checks: ['MEDIA_RIGHTS'] }];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    let body: unknown = proposals;
    if (path.endsWith('/approve')) { proposals = proposals.slice(1); body = { id: contentId, status: 'APPROVED' }; }
    else if (path.includes('/accesstrade/products')) body = [{ product_id: 'p1', name: 'Váy maxi hoa', url: 'https://shopee.vn/vay-1', merchant: 'shopee', price: 299000, discount: 199000, image: null }];
    else if (path.endsWith('/accesstrade/import')) body = { program_id: '00000000-0000-4000-8000-000000000054', skipped: [], links: [{ id: '00000000-0000-4000-8000-000000000055',
      program_id: '00000000-0000-4000-8000-000000000054', product_id: null, label: 'Váy maxi hoa', original_url: 'https://shorten.asia/a', tracking_params: {}, final_url: 'https://shorten.asia/a', status: 'ACTIVE' }] };
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}>{node}</QueryClientProvider></MemoryRouter>);
}

it('lists ready proposals first and approves one with a note', async () => {
  wrap(<Proposals token="owner"/>);
  const cards = await screen.findAllByTestId('proposal');
  expect(within(cards[0]).getByText('Váy maxi')).toBeInTheDocument();
  expect(within(cards[1]).getByText(/Chưa qua/)).toHaveTextContent('MEDIA_RIGHTS');
  expect(within(cards[1]).getByRole('button', { name: 'Duyệt' })).toBeDisabled();
  fireEvent.change(within(cards[0]).getByLabelText('Ghi chú quyết định'), { target: { value: 'Ổn' } });
  fireEvent.click(within(cards[0]).getByRole('button', { name: 'Duyệt' }));
  await waitFor(() => expect(screen.getAllByTestId('proposal')).toHaveLength(1));
  expect(posts()).toEqual([{ path: `/campaigns/${campaignId}/content/${contentId}/approve`, body: { note: 'Ổn' } }]);
});

it('loads ACCESSTRADE products and creates links for the chosen ones', async () => {
  const client = new QueryClient();
  const { result } = renderHook(() => useCampaignApi('owner'), { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
  wrap(<AccesstradeImport api={result.current} campaignId={campaignId} editable/>);
  fireEvent.click(screen.getByRole('button', { name: 'Tải sản phẩm' }));
  fireEvent.click(await screen.findByLabelText(/Váy maxi hoa · 199.000đ/));
  fireEvent.click(screen.getByRole('button', { name: 'Tạo link cho 1 sản phẩm' }));
  expect(await screen.findByText('Đã tạo 1 link affiliate.')).toBeInTheDocument();
  expect(posts()[0]).toEqual({ path: `/campaigns/${campaignId}/accesstrade/import`, body: { merchant: 'shopee', products: [{ product_id: 'p1', name: 'Váy maxi hoa', url: 'https://shopee.vn/vay-1', price: 299000, discount: 199000 }] } });
});
