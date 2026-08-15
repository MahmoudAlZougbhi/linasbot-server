/** Tenant services with priced options — mobile API. */

import { z } from 'zod';

import { apiFetch } from '../../api/client';

const ServiceOptionSchema = z.object({
  id: z.string().optional(),
  machine_name: z.string().nullable().optional(),
  body_part: z.string().nullable().optional(),
  staff_name: z.string().nullable().optional(),
  price: z.string(),
  currency: z.string().optional(),
  sort_order: z.number().optional(),
});

export const ServiceSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    active: z.boolean().optional(),
    options: z.array(ServiceOptionSchema).optional(),
    price_summary: z.string().nullable().optional(),
    created_at: z.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
  })
  .passthrough();

export type ServiceOption = z.infer<typeof ServiceOptionSchema>;
export type Service = z.infer<typeof ServiceSchema>;

export type ServiceOptionInput = {
  id?: string;
  machine_name?: string | null;
  body_part?: string | null;
  staff_name?: string | null;
  price: string;
  currency?: string;
  sort_order?: number;
};

export type ServiceWriteInput = {
  name: string;
  active?: boolean;
  options: ServiceOptionInput[];
};

const ListSchema = z
  .object({
    success: z.literal(true),
    services: z.array(ServiceSchema),
    total: z.number(),
  })
  .passthrough();

const OneSchema = z
  .object({
    success: z.literal(true),
    service: ServiceSchema,
  })
  .passthrough();

export async function fetchServices(): Promise<{ services: Service[]; total: number }> {
  const body = await apiFetch('/api/mobile/services', { method: 'GET', schema: ListSchema });
  return { services: body.services, total: body.total };
}

export async function fetchService(serviceId: string): Promise<Service> {
  const body = await apiFetch(`/api/mobile/services/${serviceId}`, {
    method: 'GET',
    schema: OneSchema,
  });
  return body.service;
}

export async function createService(input: ServiceWriteInput): Promise<Service> {
  const body = await apiFetch('/api/mobile/services', {
    method: 'POST',
    schema: OneSchema,
    body: JSON.stringify(input),
  });
  return body.service;
}

export async function updateService(serviceId: string, input: ServiceWriteInput): Promise<Service> {
  const body = await apiFetch(`/api/mobile/services/${serviceId}`, {
    method: 'PUT',
    schema: OneSchema,
    body: JSON.stringify(input),
  });
  return body.service;
}

export async function deleteService(serviceId: string): Promise<void> {
  await apiFetch(`/api/mobile/services/${serviceId}`, {
    method: 'DELETE',
    schema: z.object({ success: z.literal(true) }).passthrough(),
  });
}

export function emptyOptionRow(): ServiceOptionInput {
  return {
    machine_name: '',
    body_part: '',
    staff_name: '',
    price: '',
    currency: 'USD',
  };
}
