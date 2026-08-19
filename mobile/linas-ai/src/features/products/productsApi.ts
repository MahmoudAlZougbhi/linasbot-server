/** AI Products mobile API — tenant-scoped catalog CRUD. */

import { z } from 'zod';

import { ApiError, apiFetch, apiUpload, isMetadataPreparationFailure } from '../../api/client';
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
    description: z.string().nullable().optional(),
    price: z.string().nullable().optional(),
    sizes: z.array(z.string()).optional(),
    colors: z.array(z.string()).optional(),
    note: z.string().nullable().optional(),
    availability: z.string().optional(),
    images: z.array(ProductImageSchema).optional(),
    links: z.array(ProductLinkSchema).optional(),
    created_at: z.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
  })
  .passthrough();

export type Product = z.infer<typeof ProductSchema>;

export type ProductWriteInput = {
  name: string;
  description?: string | null;
  price?: string | null;
  sizes: string[];
  colors: string[];
  note?: string | null;
  availability?: string;
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

/** Instant list stock toggle — full product rewrite preserving media/links. */
export async function updateProductAvailability(
  product: Product,
  availability: 'in_stock' | 'out_of_stock',
): Promise<Product> {
  return updateProduct(product.id, {
    name: product.name,
    description: product.description ?? null,
    price: product.price ?? null,
    sizes: product.sizes ?? [],
    colors: product.colors ?? [],
    note: product.note ?? null,
    availability,
    images: (product.images ?? []).map((img, index) => ({
      media_id: img.media_id,
      sort_order: img.sort_order ?? index,
    })),
    links: (product.links ?? []).map((link, index) => ({
      url: link.url,
      label: link.label ?? null,
      sort_order: link.sort_order ?? index,
    })),
  });
}

export async function deleteProduct(productId: string): Promise<void> {
  await apiFetch(`/api/mobile/products/${productId}`, {
    method: 'DELETE',
    schema: z.object({ success: z.literal(true) }).passthrough(),
  });
}

const ImportPreviewSchema = z
  .object({
    success: z.literal(true),
    preview: z.array(
      z
        .object({
          row: z.number(),
          name: z.string(),
          valid: z.boolean().optional(),
        })
        .passthrough(),
    ),
    valid_count: z.number(),
    error_count: z.number(),
    errors: z.array(z.object({ row: z.string(), error: z.string() })).optional(),
    import_format: z.string().optional(),
  })
  .passthrough();

const ImportResultSchema = z
  .object({
    success: z.literal(true),
    created: z.number(),
    errors: z.array(z.object({ row: z.string(), error: z.string() })).optional(),
    import_format: z.string().optional(),
  })
  .passthrough();

export async function previewProductsImport(csvText: string): Promise<{
  preview: { row: number; name: string; valid?: boolean }[];
  valid_count: number;
  error_count: number;
}> {
  const body = await apiFetch('/api/mobile/products/import/preview', {
    method: 'POST',
    schema: ImportPreviewSchema,
    body: JSON.stringify({ csv_text: csvText }),
  });
  return {
    preview: body.preview,
    valid_count: body.valid_count,
    error_count: body.error_count,
  };
}

export async function importProducts(csvText: string): Promise<{ created: number }> {
  const body = await apiFetch('/api/mobile/products/import', {
    method: 'POST',
    schema: ImportResultSchema,
    body: JSON.stringify({ csv_text: csvText }),
  });
  return { created: body.created };
}

export async function previewProductsXlsxImport(fileBase64: string): Promise<{
  preview: Array<{ row: number; name: string; valid?: boolean; availability?: string }>;
  valid_count: number;
  error_count: number;
}> {
  const body = await apiFetch('/api/mobile/products/import/xlsx/preview', {
    method: 'POST',
    schema: ImportPreviewSchema,
    body: JSON.stringify({ file_base64: fileBase64 }),
  });
  return {
    preview: body.preview,
    valid_count: body.valid_count,
    error_count: body.error_count,
  };
}

export async function importProductsXlsx(fileBase64: string): Promise<{ created: number }> {
  const body = await apiFetch('/api/mobile/products/import/xlsx', {
    method: 'POST',
    schema: ImportResultSchema,
    body: JSON.stringify({ file_base64: fileBase64 }),
  });
  return { created: body.created };
}

export async function uploadProductMedia(file: {
  uri: string;
  name: string;
  mimeType: string;
}): Promise<{ media_id: string; filename?: string; mime?: string }> {
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
    throw new ApiError('Product media upload failed', response.status, body);
  }
  const parsed = UploadSchema.parse(body);
  return { media_id: parsed.media_id, filename: parsed.filename, mime: parsed.mime };
}

/** @deprecated use uploadProductMedia */
export async function uploadProductImage(file: {
  uri: string;
  name: string;
  mimeType: string;
}): Promise<{ media_id: string }> {
  return uploadProductMedia(file);
}

export const MAX_PRODUCT_IMAGES = 5;

export function parseCommaList(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export function joinCommaList(values: string[]): string {
  return values.join(', ');
}
