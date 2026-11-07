import { cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import ContentReview from './ContentReview';
import { useCampaignApi } from './campaignApi';

const campaignId = '00000000-0000-4000-8000-000000000002';
const contentId = '00000000-0000-4000-8000-000000000009';
const version = { version_no: 1, base_version_no: null, title: 'Váy hè', body: 'Xem tại {{AFFILIATE_LINK}}', hashtags: ['vay'], cta: 'Mua ngay', author_kind: 'AI', author: 'content-agent',
  created_at: '2026-11-07T00:00:00Z', claims: [{ classification: 'FACT', statement: 'Hoa hồng 3.68%', source_ids: ['s'] }] };
const pass = (name: string) => ({ check_name: name, result: 'PASS', method: 'RULE', note: 'ok', evidence: [] });
const base = { id: contentId, content_type: 'SOCIAL_POST', current_version: version, versions: [version], publish_records: [], decided_by: null, decision_note: null };
let state: Record<string, unknown>;
const posts = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST').map(([url, init]) => ({ path: String(url).replace(/^.*\/api\/v1/, ''), body: JSON.parse(String(init?.body)) }));

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  state = { ...base, status: 'IN_REVIEW', checks: [pass('LINK_PLACEHOLDER'), { check_name: 'MEDIA_RIGHTS', result: 'NEEDS_OWNER', method: 'RULE', note: 'Confirm media rights', evidence: [] }] };
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    let body: unknown = state;
    if (path.endsWith('/attest')) state = { ...state, checks: [pass('LINK_PLACEHOLDER'), { ...pass('MEDIA_RIGHTS'), method: 'OWNER', attested_by: 'owner' }] };
    if (path.endsWith('/approve')) state = { ...state, status: 'APPROVED', decided_by: 'owner', decision_note: 'ok' };
    if (path.endsWith('/export')) { state = { ...state, status: 'READY_TO_PUBLISH' }; body = { text: 'Váy hè\n\nXem tại https://s.shopee.vn/a\n\nCó link tiếp thị liên kết.', link_url: 'https://s.shopee.vn/a', disclosure_added: true, status: 'READY_TO_PUBLISH', version_no: 1 }; }
    else if (init?.method === 'POST') body = state;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderReview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useCampaignApi('owner'), { wrapper });
  return render(<QueryClientProvider client={client}><ContentReview api={result.current} campaignId={campaignId} contentId={contentId}/></QueryClientProvider>);
}

it('requires Owner confirmation of open checks before approval, then exports with the real link', async () => {
  renderReview();
  expect(await screen.findByText('Xem tại {{AFFILIATE_LINK}}')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Ghi chú quyết định'), { target: { value: 'ok' } });
  expect(screen.getByRole('button', { name: 'Duyệt' })).toBeDisabled();
  expect(screen.getByText(/Cần xử lý trước khi duyệt/)).toHaveTextContent('Quyền dùng hình ảnh/tài liệu');
  fireEvent.change(screen.getByLabelText('Xác nhận của Owner'), { target: { value: 'Ảnh tự chụp' } });
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Duyệt' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Duyệt' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Xuất văn bản' }));
  expect(await screen.findByTestId('export-text')).toHaveValue('Váy hè\n\nXem tại https://s.shopee.vn/a\n\nCó link tiếp thị liên kết.');
  expect(posts().map(call => call.path)).toEqual([`/campaigns/${campaignId}/content/${contentId}/checks/MEDIA_RIGHTS/attest`, `/campaigns/${campaignId}/content/${contentId}/approve`,
    `/campaigns/${campaignId}/content/${contentId}/export`]);
  expect(posts()[0].body).toEqual({ note: 'Ảnh tự chụp' });
  expect(await screen.findByLabelText('Link bài đăng')).toBeInTheDocument();
});

it('saves an Owner edit as a new version based on the current one', async () => {
  renderReview();
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa' }));
  fireEvent.change(screen.getByLabelText('Nội dung (giữ nguyên {{AFFILIATE_LINK}})'), { target: { value: 'Mới {{AFFILIATE_LINK}}' } });
  fireEvent.change(screen.getByLabelText('Hashtag'), { target: { value: 'vay, he' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản mới' }));
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0]).toEqual({ path: `/campaigns/${campaignId}/content/${contentId}/versions`, body: { base_version_no: 1, title: 'Váy hè', body: 'Mới {{AFFILIATE_LINK}}', cta: 'Mua ngay', hashtags: ['vay', 'he'] } });
});

it('explains a failed check and offers only edit or reject', async () => {
  state = { ...state, status: 'CHECK_FAILED', checks: [{ check_name: 'PLATFORM_POLICY', result: 'FAIL', method: 'RULE', note: 'Remove guarantees', evidence: ['cam kết'] }] };
  renderReview();
  expect(await screen.findByText('Không đạt')).toBeInTheDocument();
  expect(screen.getByText('cam kết')).toBeInTheDocument();
  expect(screen.getByText(/Có kiểm tra không đạt/)).toHaveAttribute('role', 'alert');
  expect(screen.queryByRole('button', { name: 'Duyệt' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Từ chối' })).toBeDisabled();
});
