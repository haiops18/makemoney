import { cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import { PostingSchedule } from './CampaignAutopilot';
import { useCampaignApi } from './campaignApi';

const campaignId = '00000000-0000-4000-8000-000000000061';
const pageId = '00000000-0000-4000-8000-000000000062';
let schedule: Record<string, unknown>;
const calls = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method).map(([url, init]) => ({ path: String(url).replace(/^.*\/api\/v1/, ''), method: init?.method, body: JSON.parse(String(init?.body)) }));

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  schedule = { configured: false, enabled: false, hours: [] };
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    let body: unknown = [];
    if (path === '/integrations') body = [{ id: pageId, kind: 'FACEBOOK_PAGE', label: 'Trang váy', last_check_status: 'OK' }];
    else if (path.endsWith('/schedule')) { if (init?.method === 'PUT') schedule = { ...JSON.parse(String(init.body)), configured: true, paused_reason: null }; body = schedule; }
    else if (path.endsWith('/scheduled-posts')) body = [{ id: '00000000-0000-4000-8000-000000000063', content_id: '00000000-0000-4000-8000-000000000064', version_no: 1,
      slot_at: '2026-11-08T13:00:00Z', status: 'POSTED', attempted_at: '2026-11-08T13:00:05Z', external_post_id: '123_456', error: null, title: 'Váy maxi' }];
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('turns automatic posting on only after an explicit confirmation and shows posted items', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { result } = renderHook(() => useCampaignApi('owner'), { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
  render(<QueryClientProvider client={client}><PostingSchedule api={result.current} campaignId={campaignId} active/></QueryClientProvider>);
  expect(await screen.findByText(/facebook.com\/123_456/)).toBeInTheDocument();
  fireEvent.click(await screen.findByLabelText('12h'));
  fireEvent.click(screen.getByRole('button', { name: 'Bật lịch tự đăng' }));
  expect(confirm.mock.calls[0][0]).toContain('TỰ ĐỘNG đăng lên Facebook Page');
  expect(calls()).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: 'Bật lịch tự đăng' }));
  await waitFor(() => expect(calls()).toHaveLength(1));
  expect(calls()[0]).toEqual({ path: `/campaigns/${campaignId}/schedule`, method: 'PUT', body: { integration_id: pageId, enabled: true, hours: [8, 12, 20] } });
  expect(await screen.findByText('Đang bật')).toBeInTheDocument();
});
