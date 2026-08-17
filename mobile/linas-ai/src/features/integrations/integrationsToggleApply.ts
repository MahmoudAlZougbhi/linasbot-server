import { ApiError, apiFetch } from '../../api/client';
import {
  defaultToggles,
  type IntegrationRow,
} from './IntegrationChannelCard';
import { ToggleResponseSchema, type IntegrationListRow } from './integrationsSchemas';

type Row = IntegrationListRow;

export function mergeToggleResponse(row: Row, res: {
  toggles: Row['toggles'];
  comments_state?: Row['comments_state'];
  dm_state?: Row['dm_state'];
}): Row {
  return {
    ...row,
    toggles: res.toggles,
    comments_state: res.comments_state ?? row.comments_state,
    dm_state: res.dm_state ?? row.dm_state,
    comments_blocker: res.comments_state?.blocker_code ?? res.comments_state?.blocker ?? undefined,
  };
}

export async function applyIntegrationToggle(args: {
  row: Row;
  key: 'dm' | 'comments';
  value: boolean;
  setRows: (updater: (curr: Row[]) => Row[]) => void;
  setBusyToggle: (value: { platform: string; key: 'dm' | 'comments' } | null) => void;
  setError: (message: string | null) => void;
  onAuthGate: () => void;
  toggleError: string;
  disconnectHint: string;
}): Promise<void> {
  const previous = defaultToggles(args.row as IntegrationRow);
  args.setBusyToggle({ platform: args.row.platform, key: args.key });
  args.setError(null);
  args.setRows((curr) =>
    curr.map((r) =>
      r.platform === args.row.platform
        ? { ...r, toggles: { ...defaultToggles(r as IntegrationRow), [args.key]: args.value } }
        : r,
    ),
  );
  try {
    const res = await apiFetch(
      `/api/mobile/integrations/${encodeURIComponent(args.row.platform)}/toggles`,
      {
        method: 'PATCH',
        body: JSON.stringify({ [args.key]: args.value }),
        schema: ToggleResponseSchema,
      },
    );
    args.setRows((curr) =>
      curr.map((r) => (r.platform === args.row.platform ? mergeToggleResponse(r, res) : r)),
    );
  } catch (err) {
    args.setRows((curr) =>
      curr.map((r) => (r.platform === args.row.platform ? { ...r, toggles: previous } : r)),
    );
    if (err instanceof ApiError && err.status === 401) args.onAuthGate();
    else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
      const body = err.body as { message?: unknown; error?: unknown; reauthorize_required?: unknown };
      const msg = body.message;
      const code = typeof body.error === 'string' ? body.error : '';
      const text = typeof msg === 'string' && msg.trim() ? msg : args.toggleError;
      args.setError(
        body.reauthorize_required === true || code === 'COMMENT_SCOPES_MISSING'
          ? `${text} ${args.disconnectHint}`
          : text,
      );
    } else args.setError(args.toggleError);
  } finally {
    args.setBusyToggle(null);
  }
}
