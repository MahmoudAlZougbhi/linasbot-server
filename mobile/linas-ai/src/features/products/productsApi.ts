/** AI Products mobile API — tenant-scoped catalog CRUD. */

import { z } from 'zod';

import { ApiError, apiFetch, apiUpload } from '../../api/client';
import { appendLocalFile } from '../../api/formDataFile';

const ProductImageSchema = z.object({
  id: z.string().optional(),
  media_id: z.string(),
  sort_order: z.number(),
});

const ProductLinkSchema = z.object({
  id: z.string().optional(),
  url: z.string(),
  label: z.string().nullable().optional(),
  sort_order: z.number().optional(),
});

export const ProductSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    price: z.string().nullable().optional(),
    sizes: z.array(z.string()).optional(),
    colors: z.array(z.string()).optional(),
    note: z.string().nullable().optional(),
    images: z.array(ProductImageSchema).optional(),
    links: z.array(ProductLinkSchema).optional(),
    created_at: z.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
  })
  .passthrough();

export type Product = z.infer<typeof ProductSchema>;

export type ProductWriteInput = {
  name: string;
  price?: string | null;
  sizes: string[];
  colors: string[];
  note?: string | null;
  images: { media_id: string; sort_order: number }[];
  links: { url: string; label?: string | null; sort_order?: number }[];
};

const ListSchema = z
  .object({
    success: z.literal(true),
    products: z.array(ProductSchema),
    total: z.number(),
  })
  .passthrough();

const OneSchema = z
  .object({
    success: z.literal(true),
    product: ProductSchema,
  })
  .passthrough();

const UploadSchema = z
  .object({
    success: z.literal(true),
    media_id: z.string(),
    filename: z.string().optional(),
    mime: z.string().optional(),
    size: z.number().optional(),
  })
  .passthrough();

export async function fetchProducts(): Promise<{ products: Product[]; total: number }> {
  const body = await apiFetch('/api/mobile/products', { method: 'GET', schema: ListSchema });
  return { products: body.products, total: body.total };
}

export async function fetchProduct(productId: string): Promise<Product> {
  const body = await apiFetch(`/api/mobile/products/${productId}`, {
    method: 'GET',
    schema: OneSchema,
  });
  return body.product;
}

export async function createProduct(input: ProductWriteInput): Promise<Product> {
  const body = await apiFetch('/api/mobile/products', {
    method: 'POST',
    schema: OneSchema,
    body: JSON.stringify(input),
  });
  return body.product;
}

export async function updateProduct(productId: string, input: ProductWriteInput): Promise<Product> {
  const body = await apiFetch(`/api/mobile/products/${productId}`, {
    method: 'PUT',
    schema: OneSchema,
    body: JSON.stringify(input),
  });
  return body.product;
}

export async function deleteProduct(productId: string): Promise<void> {
  await apiFetch(`/api/mobile/products/${productId}`, {
    method: 'DELETE',
    schema: z.object({ success: z.literal(true) }).passthrough(),
  });
}

export async function uploadProductImage(file: {
  uri: string;
  name: string;
  mimeType: string;
}): Promise<{ media_id: string }> {
  const response = await apiUpload('/api/mobile/products/media', () => {
    const form = new FormData();
    appendLocalFile(form, 'file', file.uri, { name: file.name });
    return form;
  });
  const text = await response.text();
  let body: unknown = {};
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = { raw: text };
    }
  }
  if (!response.ok) {
    throw new ApiError('Product image upload failed', response.status, body);
  }
  const parsed = UploadSchema.parse(body);
  return { media_id: parsed.media_id };
}

export const MAX_PRODUCT_IMAGES = 3;

export function parseCommaList(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export function joinCommaList(values: string[]): string {
  return values.join(', ');
}
