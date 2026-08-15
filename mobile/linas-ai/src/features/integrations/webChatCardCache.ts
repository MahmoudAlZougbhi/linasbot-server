import type { WebChatSettings } from './webChatApi';

export type WebChatCardSnapshot = {
  settings: WebChatSettings;
  entitlementWeb: boolean | null;
};

let memorySnapshot: WebChatCardSnapshot | null = null;

export function readWebChatCardSnapshot(): WebChatCardSnapshot | null {
  return memorySnapshot;
}

export function writeWebChatCardSnapshot(snapshot: WebChatCardSnapshot): void {
  memorySnapshot = snapshot;
}

export function clearWebChatCardSnapshot(): void {
  memorySnapshot = null;
}
