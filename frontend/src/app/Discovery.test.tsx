import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import Discovery from './Discovery';

const runId = '00000000-0000-4000-8000-000000000041';
const workflowId = '00000000-0000-4000-8000-000000000042';
const idea = { summary: 'So sánh giày', how_it_works: ['Chọn sản phẩm', 'Đăng bài'], income_low_vnd: 500000, income_base_vnd: 4000000, income_high_vnd: 9000000, startup_cost_vnd: 0,
  monthly_cost_vnd: 100000, weeks_to_first_income: 4, hours_per_week: 6, success_likelihood: 30, risk_level: 'MEDIUM', risks: ['Tiếp cận thấp'], required_integrations: ['FACEBOOK_PAGE'],
  assumptions: ['Hoa hồng 3-8%'] };
const candidate = { id: '00000000-0000-4000-8000-000000000043', title: 'So sánh giày nữ', business_model: 'AFFILIATE', status: 'PROPOSED', rank_value: 1200000, data: idea,
  decided_by: null, decision_note: null, opportunity_id: null };
const summary = { run_id: runId, topic: 'thời trang nữ', target_market: 'Việt Nam', max_cost_usd: '2.000000', workflow_id: workflowId, workflow_status: 'COMPLETED', source_count: 4,
  candidate_count: 1, created_at: '2026-11-08T13:00:00Z' };
let detail: Record<string, unknown>;
let integrations: unknown[];
const posts = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST').map(([url, init]) => ({ path: String(url).replace(/^.*\/api\/v1/, ''), body: JSON.parse(String(init?.body)) }));

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  integrations = [{ kind: 'SEARCH_TAVILY', enabled: true, has_secret: true }];
  detail = { ...summary, queries: ['thời trang nữ kiếm tiền online Việt Nam'], ranking_summary: 'Hai hướng affiliate', sources: [
    { id: '00000000-0000-4000-8000-000000000044', source_name: 'Kết quả 1', source_url: 'https://tin.example.vn/1', excerpt: 'Hoa hồng 3-8%', verification_status: 'UNVERIFIED' }], candidates: [candidate] };
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    let body: unknown = [];
    if (path === '/integrations') body = integrations;
    else if (path === '/discovery' && init?.method === 'POST') body = detail;
    else if (path === '/discovery') body = [summary];
    else if (path.endsWith('/approve')) { const decided = { ...candidate, status: 'APPROVED', decided_by: 'owner', decision_note: 'Thử', opportunity_id: '00000000-0000-4000-8000-000000000045' };
      detail = { ...detail, candidates: [decided] }; body = decided; }
    else if (path === `/discovery/${runId}`) body = detail;
    else if (path.endsWith('/auto-run')) body = null;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}><Discovery token="owner"/></QueryClientProvider></MemoryRouter>);
}

it('asks before paid searches, then shows the ranked idea with its estimates and lets the Owner approve it', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  renderPage();
  fireEvent.change(await screen.findByLabelText('Lĩnh vực / chủ đề'), { target: { value: 'thời trang nữ' } });
  fireEvent.change(screen.getByLabelText('Số lượt tìm kiếm'), { target: { value: '2' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Tìm cơ hội' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Tìm cơ hội' }));
  expect(confirm).toHaveBeenCalledWith('App sẽ dùng 2 lượt tìm kiếm web có tính phí của nguồn tìm kiếm anh/chị đã kết nối. Tiếp tục?');
  expect(await screen.findByText(/Đã tìm được 4 nguồn/)).toBeInTheDocument();
  expect(posts()[0]).toEqual({ path: '/discovery', body: { topic: 'thời trang nữ', target_market: 'Việt Nam', budget_note: null, max_cost_usd: '2', query_count: 2, results_per_query: 4 } });
  const card = await screen.findByTestId('candidate');
  expect(within(card).getByText('So sánh giày nữ')).toBeInTheDocument();
  expect(within(card).getByText('30%')).toBeInTheDocument();
  expect(within(card).getByText(/500\.000đ – 9\.000\.000đ/)).toBeInTheDocument();
  expect(screen.getByText(/không phải cam kết thu nhập/)).toBeInTheDocument();
  const approve = within(card).getByRole('button', { name: 'Duyệt hướng này' });
  expect(approve).toBeDisabled();
  fireEvent.change(within(card).getByLabelText('Ghi chú quyết định'), { target: { value: 'Thử' } });
  fireEvent.click(approve);
  expect(await screen.findByRole('link', { name: 'Tạo chiến dịch từ cơ hội này' })).toBeInTheDocument();
  expect(posts()[1]).toEqual({ path: `/discovery/${runId}/candidates/${candidate.id}/approve`, body: { note: 'Thử' } });
});

it('points to the Integrations page when no search source is connected', async () => {
  integrations = [];
  renderPage();
  expect(await screen.findByRole('link', { name: 'Kết nối Tavily hoặc Brave Search' })).toHaveAttribute('href', '/integrations');
  expect(screen.getByRole('button', { name: 'Tìm cơ hội' })).toBeDisabled();
});
