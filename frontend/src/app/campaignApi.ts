import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

const evidence = z.enum(['VERIFIED', 'UNVERIFIED', 'REJECTED', 'UNSOURCED']);
export type Evidence = z.infer<typeof evidence>;
export const campaignSchema = z.object({
  id: z.string().uuid(), opportunity_id: z.string().uuid(), name: z.string(), business_model: z.string(), niche: z.string().nullable(), target_audience: z.string().nullable(),
  goal: z.string().nullable(), language: z.enum(['vi', 'en']), disclosure_text: z.string().nullable(), max_cost_usd: z.string(),
  status: z.enum(['DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED']), version: z.number(), created_at: z.string(),
});
export type Campaign = z.infer<typeof campaignSchema>;
export const sourceSchema = z.object({
  id: z.string().uuid(), source_name: z.string(), source_url: z.string().nullable(), excerpt: z.string(), captured_at: z.string(),
  verification_status: z.enum(['UNVERIFIED', 'VERIFIED', 'REJECTED']), verified_by: z.string().nullable().optional(), verification_note: z.string().nullable().optional(),
});
export type Source = z.infer<typeof sourceSchema>;
export const termSchema = z.object({ id: z.string().uuid(), term: z.string(), value_text: z.string(), value_numeric: z.string().nullable(), unit: z.string(), source_id: z.string().uuid().nullable(), evidence_status: evidence });
export const programSchema = z.object({ id: z.string().uuid(), network: z.string(), name: z.string(), join_url: z.string().nullable(), link_hosts: z.array(z.string()), tracking_param_keys: z.array(z.string()), terms: z.array(termSchema) });
export type Program = z.infer<typeof programSchema>;
export const productSchema = z.object({ id: z.string().uuid(), name: z.string(), merchant: z.string().nullable(), product_url: z.string().nullable(), price_text: z.string().nullable(), price_source_id: z.string().uuid().nullable(), price_evidence_status: evidence });
export type Product = z.infer<typeof productSchema>;
export const linkSchema = z.object({ id: z.string().uuid(), program_id: z.string().uuid(), product_id: z.string().uuid().nullable(), label: z.string(), original_url: z.string(), tracking_params: z.record(z.string(), z.string()), final_url: z.string(), status: z.enum(['ACTIVE', 'RETIRED']) });
export type AffiliateLink = z.infer<typeof linkSchema>;

export type Tr = (vi: string, en: string) => string;

export function useTr(): { tr: Tr; locale: string } {
  const { i18n } = useTranslation();
  const vi = i18n.language.startsWith('vi');
  return { tr: (a, b) => (vi ? a : b), locale: vi ? 'vi-VN' : 'en-US' };
}

/** Campaign API access. A failed POST keeps its Idempotency-Key so a retry cannot duplicate it. */
export function useCampaignApi(token: string) {
  const cache = useQueryClient();
  const retry = useRef<{ signature: string; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1`;
  const request = useCallback(async (path: string, init?: RequestInit): Promise<unknown> => {
    const response = await fetch(`${base}${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...init?.headers } });
    if (!response.ok) {
      let detail = '';
      try { const body = await response.json(); detail = typeof body?.detail === 'string' ? body.detail : ''; } catch { /* non-JSON error body */ }
      throw new Error(detail || `API ${response.status}`);
    }
    return response.json();
  }, [base, token]);
  const send = useCallback(async <T,>(method: 'POST' | 'PATCH' | 'PUT', path: string, body: unknown, schema: z.ZodType<T>): Promise<T> => {
    const serialized = JSON.stringify(body ?? {});
    const signature = `${method}:${path}:${serialized}`;
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    setBusy(true);
    try {
      const result = schema.parse(await request(path, { method, headers: { 'Idempotency-Key': retry.current.key }, body: serialized }));
      retry.current = null;
      await cache.invalidateQueries({ queryKey: ['campaigns'] });
      return result;
    } finally { setBusy(false); }
  }, [cache, request]);
  return { request, send, busy };
}

export const evidenceLabel = (status: Evidence, tr: Tr) => ({
  VERIFIED: tr('Nguồn đã xác minh', 'Verified source'), UNVERIFIED: tr('Nguồn chưa xác minh', 'Unverified source'),
  REJECTED: tr('Nguồn bị từ chối', 'Rejected source'), UNSOURCED: tr('Chưa có nguồn', 'No source'),
})[status];
