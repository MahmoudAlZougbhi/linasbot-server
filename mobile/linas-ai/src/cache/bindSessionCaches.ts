import { cacheClear } from './queryCache';
import { onSessionReset } from './sessionReset';
import { clearAuthImageCache } from './authImageCache';
import { clearCmDraftCache } from '../features/cm/cmDraftCache';
import { clearWebChatCardSnapshot } from '../features/integrations/webChatCardCache';
import { clearDrawerSessionCache } from '../features/nav/drawerSessionCache';

/** Wire feature caches to logout / tenant switch. Imported from AppShell. */
onSessionReset(() => {
  cacheClear();
  clearAuthImageCache();
  clearCmDraftCache();
  clearWebChatCardSnapshot();
  clearDrawerSessionCache();
});
