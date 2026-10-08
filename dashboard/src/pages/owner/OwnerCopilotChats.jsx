// @ts-nocheck
import { Link } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { formatRelative, formatDateTime } from './lib/format';
import { replyHtml } from './replyFormat';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Button from './ui/Button';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import TechDetails from './ui/TechDetails';
import { SkeletonRows } from './ui/Skeleton';
import { ChatBubbleOvalLeftEllipsisIcon } from '@heroicons/react/24/outline';

export default function OwnerCopilotChats() {
  const state = useLoad(() => ownerApi.listTraces({ brain: 'owner_copilot' }).then((data) => data.traces || []), []);
  return (
    <div className="space-y-6">
      <PageHeader title="Copilot chats" subtitle="Questions business owners asked the Owner Copilot, and its answers." />
      {state.status === 'loading' ? <SkeletonRows /> : null}
      {state.status === 'error' ? <Alert title="We couldn't load Copilot chats." detail={state.error} /> : null}
      {state.status === 'ready' && state.data.length === 0 ? (
        <EmptyState icon={<ChatBubbleOvalLeftEllipsisIcon className="h-6 w-6" />} title="No Copilot chats yet" text="When a business owner asks the Copilot something, it appears here." action={<Link to="/owner/brains?ai=copilot"><Button variant="secondary">Try the Copilot</Button></Link>} />
      ) : null}
      {(state.data || []).map((row) => (
        <Card key={row.id} title={row.payload?.user_message || 'Question'}>
          <p className="text-[13px] text-slate-600" title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</p>
          <p className="mt-2 text-sm" dir="auto" dangerouslySetInnerHTML={replyHtml(row.payload?.reply || '')} />
          <Link className="mt-3 inline-block text-sm text-[#0F766E]" to={`/owner/traces?id=${row.id}`}>View trace</Link>
          <TechDetails text={JSON.stringify({ model: row.payload?.model, tokens_in: row.tokens_in, tokens_out: row.tokens_out })} />
        </Card>
      ))}
    </div>
  );
}
