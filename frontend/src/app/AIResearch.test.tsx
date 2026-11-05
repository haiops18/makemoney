import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import AIResearch from './AIResearch';

const id = '00000000-0000-4000-8000-000000000001';
const created = { id, objective: 'Test research', category: null, target_market: null, target_customers: null, max_cost_usd: '1.000000', status: 'DRAFT', created_at: '2026-11-04T00:00:00Z' };
beforeEach(async () => {
  await i18n.changeLanguage('vi');
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => ({ ok: true, json: async () => init?.method === 'POST' ? created : [] }) as Response));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const renderPage = (token = 'owner') => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><AIResearch token={token}/></MemoryRouter></QueryClientProvider>);

it('requires sign in and does not fabricate research output', () => {
  renderPage('');
  expect(screen.getByText('Vui lòng đăng nhập Owner.')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it('creates an idempotent research draft and shows unverified source entry', async () => {
  renderPage();
  fireEvent.change(screen.getByLabelText('Mục tiêu nghiên cứu'), { target: { value: 'Test research' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo bản nháp' }));
  await waitFor(() => expect(screen.getByText('Đã lưu bản nháp.')).toBeInTheDocument());
  expect(screen.getByText('Các nguồn chưa xác minh và không được tự động truy cập.')).toBeInTheDocument();
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST');
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
});

it('creates a workflow draft linked to research without starting execution', async () => {
  const workflowId = '00000000-0000-4000-8000-000000000002';
  let linked = false;
  vi.mocked(fetch).mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
    if (String(url).endsWith('/workflow')) {
      if (init?.method === 'POST') { linked = true; return { ok: true, status: 201, json: async () => ({ id: workflowId, research_run_id: id, status: 'DRAFT' }) } as Response; }
      return linked ? { ok: true, status: 200, json: async () => ({ id: workflowId, research_run_id: id, status: 'DRAFT' }) } as Response : { ok: false, status: 404 } as Response;
    }
    return { ok: true, status: 200, json: async () => init?.method === 'POST' ? created : [] } as Response;
  });
  renderPage();
  fireEvent.change(screen.getByLabelText('Mục tiêu nghiên cứu'), { target: { value: 'Test research' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo bản nháp' }));
  const name = await screen.findByLabelText('Tên workflow nghiên cứu');
  fireEvent.change(name, { target: { value: 'Research flow' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo workflow nghiên cứu' }));
  expect(await screen.findByText('Đã tạo workflow bản nháp.')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Mở Workflow' })).toHaveAttribute('href', '/workflows');
});
