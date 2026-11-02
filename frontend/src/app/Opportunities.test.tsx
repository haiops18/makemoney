import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import '../i18n';
import Opportunities from './Opportunities';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('refetches after create even when the initial list request is still in flight', async () => {
  const created = { id: '00000000-0000-4000-8000-000000000001', title: 'New research', business_model: 'MICRO_SAAS', target_market: null, description: null, status: 'DRAFT', score: null, risk_level: 'UNKNOWN' };
  let lists = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    let body: unknown;
    if (url.endsWith('/summary')) body = { total: 1, high_priority: 0, promising: 0, needs_research: 0, disqualified: 0, evaluated: 0, average_score: null };
    else if (init?.method === 'POST') body = created;
    else { lists++; if (lists === 1) return new Promise<Response>(() => {}); body = { items: [created], total: 1 }; }
    return { ok: true, json: async () => body };
  }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Opportunities token="test-only"/></QueryClientProvider>);
  await waitFor(() => expect(lists).toBe(1));
  fireEvent.change(screen.getByLabelText('Tên cơ hội'), { target: { value: 'New research' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo cơ hội' }));
  expect(await screen.findByRole('button', { name: 'New research' })).toBeInTheDocument();
  expect(lists).toBe(2);
});
