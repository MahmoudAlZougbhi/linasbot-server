/** Chat screen wiring spans ChatScreen.tsx + useChatScreenController.ts after line-limit split. */

export function readChatScreenBundle(read) {
  return [
    read('features/chat/ChatScreen.tsx'),
    read('features/chat/useChatScreenController.ts'),
  ].join('\n');
}
