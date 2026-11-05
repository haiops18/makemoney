import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import AIResearchStages from './AIResearchStages';

const runId = '00000000-0000-4000-8000-000000000001';
const workflowId = '00000000-0000-4000-8000-000000000002';
const stage = (task_type: string, output: unknown) => ({ task_id: crypto.randomUUID(), name: task_type, task_type, assigned_role: 'ceo', task_status: 'SUCCEEDED', invocation_id: null, invocation_status: 'SUCCEEDED', model_id: 'gpt-test', error_code: null, estimated_cost: '0.000100', calculated_cost: '0.000020', confirmed_cost: null, output, completed_at: null });
const report = { summary: 'Recommend a pilot', findings: [{ classification: 'ESTIMATE', statement: 'Setup cost 100 USD', source_ids: [], assumptions: ['No ads'] }] };
const renderStages = (status = 'DRAFT') => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><AIResearchStages token="owner" runId={runId} workflowStatus={status}/></MemoryRouter></QueryClientProvider>);

beforeEach(async () => { await i18n.changeLanguage('vi'); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('adds AI stages to a draft without running them', async () => {
  let added = false;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') { added = true; return { ok: true, status: 201, json: async () => ({ workflow_id: workflowId, tasks: [{ id: workflowId }] }) } as Response; }
    return { ok: true, status: 200, json: async () => ({ workflow_id: workflowId, workflow_status: 'DRAFT', opportunity_id: null, stages: added ? [{ ...stage('AI_RESEARCH_PLAN', null), task_status: 'PENDING', invocation_status: null, estimated_cost: null, calculated_cost: null }] : [] }) } as Response;
  }));
  renderStages();
  fireEvent.click(await screen.findByRole('button', { name: 'Thêm giai đoạn AI' }));
  expect(await screen.findByText('Đã thêm các giai đoạn AI vào workflow bản nháp.')).toBeInTheDocument();
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST');
  expect(String(call?.[0])).toMatch(/\/pipeline$/);
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ confirm_no_execution: true });
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
  expect(await screen.findByText('AI_RESEARCH_PLAN · PENDING')).toBeInTheDocument();
});

it('labels AI output as unverified and promotes a completed report after backend confirmation', async () => {
  let promoted = false;
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') { promoted = true; return { ok: true, status: 201, json: async () => ({ research_run_id: runId, opportunity_id: workflowId, evidence_count: 1 }) } as Response; }
    return { ok: true, status: 200, json: async () => ({ workflow_id: workflowId, workflow_status: 'COMPLETED', opportunity_id: promoted ? workflowId : null, stages: [stage('AI_RESEARCH_REPORT', report)] }) } as Response;
  }));
  renderStages('COMPLETED');
  expect(await screen.findByText('Recommend a pilot')).toBeInTheDocument();
  expect(screen.getByText(/Kết quả AI là phân tích chưa xác minh/)).toBeInTheDocument();
  expect(screen.getByText(/chưa đối soát/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Tiêu đề cơ hội'), { target: { value: 'Pilot' } });
  fireEvent.change(screen.getByLabelText('Mô hình kinh doanh'), { target: { value: 'MICRO_SAAS' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo cơ hội' }));
  await waitFor(() => expect(screen.getByText('Đã tạo cơ hội từ nghiên cứu này.')).toBeInTheDocument());
  expect(screen.queryByRole('button', { name: 'Tạo cơ hội' })).not.toBeInTheDocument();
});

it('shows backend refusal details instead of pretending success', async () => {
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
    ? { ok: false, status: 409, json: async () => ({ detail: 'An enabled AI profile is required for the research agent' }) } as Response
    : { ok: true, status: 200, json: async () => ({ workflow_id: workflowId, workflow_status: 'DRAFT', opportunity_id: null, stages: [] }) } as Response));
  renderStages();
  fireEvent.click(await screen.findByRole('button', { name: 'Thêm giai đoạn AI' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('An enabled AI profile is required for the research agent');
});
