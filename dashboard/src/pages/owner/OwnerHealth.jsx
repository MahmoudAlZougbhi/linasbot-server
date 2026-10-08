// @ts-nocheck
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { formatTime } from './lib/format';
import { statusLabel, statusTone } from './lib/status';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Badge from './ui/Badge';
import Button from './ui/Button';
import Alert from './ui/Alert';
import TechDetails from './ui/TechDetails';

export default function OwnerHealth() {
  const state = useLoad(() => ownerApi.health(), []);
  const ok = state.data?.api === 'ok' && state.data?.database?.reachable;
  return (
    <div className="space-y-6">
      <PageHeader title="System status" subtitle="Is everything working right now?" actions={<Button variant="secondary" onClick={() => window.location.reload()}>Check again</Button>} />
      {state.status === 'error' ? <Alert title="We couldn't check the system status." detail={state.error} onRetry={() => window.location.reload()} /> : null}
      {state.status === 'ready' ? (
        <Card>
          <p className={`text-base font-semibold ${ok ? 'text-green-800' : 'text-red-800'}`}>{ok ? 'Everything is working' : 'Something needs attention'}</p>
          <p className="mt-4 text-sm">Portal & API <Badge tone={statusTone('health', state.data.api === 'ok')}>{statusLabel('health', state.data.api === 'ok')}</Badge></p>
          <p className="mt-2 text-sm">Database <Badge tone={statusTone('health', state.data.database?.reachable)}>{state.data.database?.reachable ? 'Connected' : 'Not reachable'}</Badge></p>
          <p className="mt-2 text-[13px] text-slate-600">Checked at {formatTime(Date.now())}</p>
          <TechDetails text={JSON.stringify(state.data, null, 2)} />
        </Card>
      ) : null}
    </div>
  );
}
