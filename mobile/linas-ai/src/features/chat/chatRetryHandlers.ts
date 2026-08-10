/**
 * Small helpers so ChatScreen stays under the 400-line source limit.
 */

export function chatErrorLabelKey(
  error: string,
): 'retry' | 'guestWordLimit' | 'guestModelUnavailable' | 'messageFailed' {
  if (error === 'retry' || error === 'guestWordLimit' || error === 'guestModelUnavailable') {
    return error;
  }
  return 'messageFailed';
}

type RetryArgs = {
  isAuthenticated: boolean;
  streaming: boolean;
  guestSending: boolean;
  guestGated: boolean;
  content: string;
  ownerSend: (content: string) => void;
  guestSend: (content: string) => void;
  openAuth: () => void;
  scrollToBottom: () => void;
};

export function retryAssistantMessage(args: RetryArgs): void {
  if (args.isAuthenticated) {
    if (args.streaming) return;
    args.ownerSend(args.content);
    return;
  }
  if (args.guestSending) return;
  if (args.guestGated) {
    args.openAuth();
    return;
  }
  args.scrollToBottom();
  args.guestSend(args.content);
}
