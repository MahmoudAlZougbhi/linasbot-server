import { StyleSheet, View } from 'react-native';

import { LoginScreen } from '../features/auth/LoginScreen';
import { RegisterScreen } from '../features/auth/RegisterScreen';
import { BillingScreen } from '../features/billing/BillingScreen';
import { SubscriptionGateScreen } from '../features/billing/SubscriptionGateScreen';
import { UsageScreen } from '../features/billing/UsageScreen';
import { ChatScreen } from '../features/chat/ChatScreen';
import { queueSetupHandoff } from '../features/chat/pendingSetupHandoff';
import { CmScreen } from '../features/cm/CmScreen';
import { CmSectionScreen } from '../features/cm/CmSectionScreen';
import type { CmProposalReview } from '../features/cm/cmProposalReview';
import type { ControlArea } from '../features/control/controlAreas';
import { DashboardScreen } from '../features/dashboard/DashboardScreen';
import { FaqRoute } from '../features/faq/FaqRoute';
import { IntegrationsScreen } from '../features/integrations/IntegrationsScreen';
import { LiveChatScreen } from '../features/livechat/LiveChatScreen';
import { NotificationsScreen } from '../features/notifications/NotificationsScreen';
import { SettingsScreen } from '../features/settings/SettingsScreen';
import { SimpleResourceScreen } from '../features/shared/SimpleResourceScreen';
import { UsersScreen } from '../features/users/UsersScreen';
import { KeepMountedPane } from './KeepMountedPane';
import type { Screen } from './navigation';

type Props = {
  screen: Screen;
  authEpoch: number;
  hasAccess: boolean;
  isPlatformOwner: boolean;
  showSubGate: boolean;
  subGateLoading: boolean;
  onOpenArea: (area: ControlArea) => void;
  onOpenCmReview: (review: CmProposalReview) => void;
  setScreen: (screen: Screen) => void;
  setResumeArea: (area: ControlArea | null) => void;
  afterLogin: () => void;
  logout: () => void;
  refreshSubGate: () => Promise<void>;
};

/** Renders keep-mounted module panes + ephemeral routes (login, cm_section, …). */
export function AppScreenTree({
  screen,
  authEpoch,
  hasAccess,
  isPlatformOwner,
  showSubGate,
  subGateLoading,
  onOpenArea,
  onOpenCmReview,
  setScreen,
  setResumeArea,
  afterLogin,
  logout,
  refreshSubGate,
}: Props) {
  const name = screen.name;
  const chatActive = !showSubGate && name === 'chat';

  return (
    <View style={styles.root}>
      {name === 'login' ? (
        <LoginScreen
          onLoggedIn={() => void afterLogin()}
          onGoRegister={() => setScreen({ name: 'register' })}
          onBack={() => setScreen({ name: 'chat' })}
        />
      ) : null}
      {name === 'register' ? (
        <RegisterScreen
          onBack={() => setScreen({ name: 'login' })}
          onDone={() => setScreen({ name: 'login' })}
        />
      ) : null}
      {showSubGate ? (
        <SubscriptionGateScreen
          loading={subGateLoading}
          onOpenSubscription={() => setScreen({ name: 'billing' })}
          onRefresh={() => void refreshSubGate()}
          onLogout={() => void logout()}
        />
      ) : null}

      <KeepMountedPane key={`chat-${authEpoch}`} active={chatActive}>
        <ChatScreen
          isAuthenticated={hasAccess}
          isPlatformOwner={isPlatformOwner}
          onOpenArea={onOpenArea}
          onOpenCmReview={onOpenCmReview}
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`settings-${authEpoch}`} active={name === 'settings'}>
        <SettingsScreen
          onBack={() => setScreen({ name: 'chat' })}
          onLogout={() => void logout()}
          onOpenNotifications={() => setScreen({ name: 'notifications', backTo: 'settings' })}
          onOpenActions={() =>
            setScreen({ name: 'cm_section', section: 'actions', backTo: 'settings' })
          }
          onOpenAiLimits={() =>
            setScreen({ name: 'cm_section', section: 'ai_limits', backTo: 'settings' })
          }
        />
      </KeepMountedPane>
      <KeepMountedPane key={`integrations-${authEpoch}`} active={name === 'integrations'}>
        <IntegrationsScreen
          onBack={() => setScreen({ name: 'chat' })}
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`users-${authEpoch}`} active={name === 'users'}>
        <UsersScreen
          onBack={() => setScreen({ name: 'chat' })}
          onRequestLogin={() => {
            setResumeArea('users');
            setScreen({ name: 'login' });
          }}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`dashboard-${authEpoch}`} active={name === 'dashboard'}>
        <DashboardScreen onBack={() => setScreen({ name: 'chat' })} isPlatformOwner={isPlatformOwner} />
      </KeepMountedPane>
      <KeepMountedPane key={`billing-${authEpoch}`} active={name === 'billing'}>
        <BillingScreen
          onBack={() => {
            void refreshSubGate().then(() => setScreen({ name: 'chat' }));
          }}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`usage-${authEpoch}`} active={name === 'usage'}>
        <UsageScreen onBack={() => setScreen({ name: 'chat' })} />
      </KeepMountedPane>
      <KeepMountedPane key={`livechat-${authEpoch}`} active={name === 'livechat'}>
        <LiveChatScreen
          onBack={() => setScreen({ name: 'chat' })}
          initialOpen={name === 'livechat' ? (screen.open ?? null) : null}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`notifications-${authEpoch}`} active={name === 'notifications'}>
        <NotificationsScreen
          isAuthenticated={hasAccess}
          onBack={() => {
            if (name === 'notifications' && screen.backTo === 'settings') {
              setScreen({ name: 'settings' });
            } else {
              setScreen({ name: 'chat' });
            }
          }}
          onOpenLiveChat={(target) => setScreen({ name: 'livechat', open: target })}
          onRequestLogin={() => {
            setResumeArea('notifications');
            setScreen({ name: 'login' });
          }}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`cm-${authEpoch}`} active={name === 'cm'}>
        <CmScreen
          onBack={() => setScreen({ name: 'chat' })}
          onOpenSection={(section) => setScreen({ name: 'cm_section', section, backTo: 'cm' })}
          onContinueSetup={(prompt) => {
            queueSetupHandoff({ text: prompt, mode: 'work', autoSend: true });
            setScreen({ name: 'chat' });
          }}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`faq-${authEpoch}`} active={name === 'faq'}>
        <FaqRoute
          onBack={() => setScreen({ name: 'chat' })}
          onGoChat={() => setScreen({ name: 'chat' })}
          proposalReview={name === 'faq' ? (screen.proposalReview ?? null) : null}
        />
      </KeepMountedPane>

      {name === 'cm_section' ? (
        <CmSectionScreen
          section={screen.section}
          proposalReview={screen.proposalReview ?? null}
          onBack={() => {
            if (screen.backTo === 'settings') {
              setScreen({ name: 'settings' });
              return;
            }
            if (screen.backTo === 'chat') {
              setScreen({ name: 'chat' });
              return;
            }
            setScreen({ name: 'cm' });
          }}
          backLabel={
            screen.backTo === 'settings'
              ? '← Back to Settings'
              : screen.backTo === 'chat'
                ? '← Back to chat'
                : '← Back to Content Management'
          }
        />
      ) : null}
      {name === 'resource' ? (
        <SimpleResourceScreen
          title={screen.title}
          path={screen.path}
          onBack={() => setScreen({ name: 'chat' })}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
