import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, it, expect, vi } from 'vitest';
import '../i18n';
import { OpportunityDetail, OpportunityComparison } from './OpportunityDetail';

afterEach(cleanup);
const wrap = (child: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>{child}</QueryClientProvider>);
const record = { title: 'Research', description: null, target_market: null, target_customer: null, monetization_method: null };

it('renders empty evidence, estimates and unknown scoring without invented values', async () => {
  wrap(<OpportunityDetail id="test" title="Research" request={vi.fn(async path => path === '/test' ? record : [])}/>);
  expect((await screen.findAllByText('UNKNOWN')).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole('button', { name: 'Kịch bản tài chính' }));
  expect(screen.getByLabelText('setup_cost')).toHaveValue('');
});

it('edits without clearing unspecified fields and provides an idempotency key', async () => {
  const request = vi.fn(async (path: string, init?: RequestInit) => init ? { id: 'test', title: 'Updated' } : path === '/test' ? record : []);
  wrap(<OpportunityDetail id="test" title="Research" request={request}/>);
  await waitFor(() => expect(request).toHaveBeenCalledWith('/test/evaluations'));
  fireEvent.change(screen.getByLabelText('title'), { target: { value: 'Updated' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu Chỉnh sửa' }));
  await screen.findByText('Đã lưu và xác minh phản hồi.');
  const call = request.mock.calls.find(([, init]) => init?.method === 'PATCH');
  expect(JSON.parse(call![1]!.body as string)).toEqual({ title: 'Updated' });
  expect((call![1]!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
});

it('shows failed detail requests and rejects comparison below two selections', async () => {
  const request = vi.fn().mockRejectedValue(new Error('API 401'));
  wrap(<OpportunityDetail id="test" title="Research" request={request}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('API 401');
  cleanup(); request.mockClear();
  wrap(<OpportunityComparison ids={[]} request={request}/>);
  await waitFor(() => expect(request).not.toHaveBeenCalled());
});

it('renders untrusted evidence as text and does not insert HTML', async () => {
  const request = vi.fn(async (path: string) => path === '/test' ? record : path.endsWith('/evidence') ? [{ id: 'evidence', source_name: 'Interview', verification_status: 'UNVERIFIED', summary: '<img src=x onerror=alert(1)>' }] : []);
  const { container } = wrap(<OpportunityDetail id="test" title="Research" request={request}/>);
  expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
  expect(container.querySelector('img')).toBeNull();
});

it('does not report success when a mutation response fails validation', async () => {
  const request = vi.fn(async (path: string, init?: RequestInit) => init ? { id: 'wrong-record', title: 'Updated' } : path === '/test' ? record : []);
  wrap(<OpportunityDetail id="test" title="Research" request={request}/>);
  await screen.findByText('Mô tả');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu Chỉnh sửa' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Lưu Chỉnh sửa' }));
  await screen.findByRole('alert');
  expect(screen.queryByText('Đã lưu và xác minh phản hồi.')).not.toBeInTheDocument();
});
