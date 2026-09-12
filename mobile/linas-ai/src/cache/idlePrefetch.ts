import { InteractionManager } from 'react-native';

import { fetchTenantDashboard } from '../features/dashboard/dashboardApi';
import { DEFAULT_DASHBOARD_PERIOD, dashboardPeriodKey } from '../features/dashboard/dashboardFormat';
import { fetchCmMeta } from '../features/cm/cmApi';
import { fetchCmSetupProgress } from '../features/cm/cmProgressApi';
import { fetchProducts } from '../features/products/productsApi';
import { ListSchema } from '../features/integrations/integrationsSchemas';
import { apiFetch } from '../api/client';
import { fetchUnifiedChats } from '../features/livechat/liveChatApi';
import { cacheGet, cacheSet, dedupeFetch, isCacheFresh } from './queryCache';
import { queryKeys } from './queryKeys';
import { QUERY_TTL } from './queryTtl';

function defaultTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

async function prefetchDashboard(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  const tz = defaultTz();
  const periodKey = dashboardPeriodKey(DEFAULT_DASHBOARD_PERIOD);
  const key = queryKeys.dashboard(periodKey, tz);
  if (isCacheFresh(key, QUERY_TTL.dashboard)) return;
  const data = await dedupeFetch(key, () => fetchTenantDashboard(DEFAULT_DASHBOARD_PERIOD, tz));
  if (signal.aborted) return;
  cacheSet(key, data);
}

async function prefetchLiveChatInbox(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  const key = queryKeys.liveChatInbox('all', 'all', '');
  if (isCacheFresh(key, QUERY_TTL.liveChatInbox)) return;
  const data = await dedupeFetch(key, () =>
    fetchUnifiedChats({ search: '', page: 1, pageSize: 30, filter: 'all', channel: 'all' }),
  );
  if (signal.aborted) return;
  cacheSet(key, data);
}

async function prefetchCmHub(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  const key = queryKeys.cmHub();
  if (isCacheFresh(key, QUERY_TTL.cmHub)) return;
  const data = await dedupeFetch(key, async () => {
    const [meta, prog, productsRes] = await Promise.all([
      fetchCmMeta(),
      fetchCmSetupProgress(),
      dedupeFetch(queryKeys.products(), fetchProducts)
        .then((res) => {
          cacheSet(queryKeys.products(), res.products);
          return res;
        })
        .catch(() => ({ products: [], total: 0 })),
    ]);
    return {
      meta,
      rows: prog.progress ?? [],
      productsComplete: (productsRes.total ?? productsRes.products.length) > 0,
      live: Boolean(prog.summary?.published ?? meta.has_published_content),
    };
  });
  if (signal.aborted) return;
  cacheSet(key, data);
}

async function prefetchIntegrations(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  const key = queryKeys.integrations();
  if (isCacheFresh(key, QUERY_TTL.integrations)) return;
  const data = await dedupeFetch(key, () => apiFetch('/api/mobile/integrations', { schema: ListSchema }));
  if (signal.aborted) return;
  cacheSet(key, data);
}

async function prefetchProducts(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  const key = queryKeys.products();
  if (isCacheFresh(key, QUERY_TTL.products)) return;
  const data = await dedupeFetch(key, () => fetchProducts());
  if (signal.aborted) return;
  cacheSet(key, data.products);
}

/**
 * After first screen is up: low-priority, cancellable, skips fresh keys.
 * Does not mount extra screens. Sequential so chat first paint is not contended.
 */
export async function prefetchEssentials(signal: AbortSignal): Promise<void> {
  const jobs = [
    prefetchDashboard,
    prefetchLiveChatInbox,
    prefetchCmHub,
    prefetchIntegrations,
    prefetchProducts,
  ];
  for (const job of jobs) {
    if (signal.aborted) return;
    try {
      await job(signal);
    } catch {
      /* prefetch never blocks or surfaces errors */
    }
  }
}

export function scheduleIdlePrefetch(signal: AbortSignal): () => void {
  const handle = InteractionManager.runAfterInteractions(() => {
    const timer = setTimeout(() => {
      void prefetchEssentials(signal);
    }, 400);
    signal.addEventListener('abort', () => clearTimeout(timer));
  });
  return () => {
    handle.cancel();
  };
}
