import { StyleSheet, View } from 'react-native';

import { LoginScreen } from '../features/auth/LoginScreen';
import { RegisterScreen } from '../features/auth/RegisterScreen';
import { BillingScreen } from '../features/billing/BillingScreen';
import { SubscriptionGateScreen } from '../features/billing/SubscriptionGateScreen';
import { ChatScreen } from '../features/chat/ChatScreen';
import { queueSetupHandoff } from '../features/chat/pendingSetupHandoff';
import { CmScreen } from '../features/cm/CmScreen';
import { CmSectionScreen } from '../features/cm/CmSectionScreen';
import type { CmProposalReview } from '../features/cm/cmProposalReview';
import type { ControlArea } from '../features/control/controlAreas';
import { DashboardScreen } from '../features/dashboard/DashboardScreen';
import { screenForDashboardTarget } from '../features/dashboard/dashboardNavigation';
import { FaqRoute } from '../features/faq/FaqRoute';
import { IntegrationsScreen } from '../features/integrations/IntegrationsScreen';
import { LiveChatScreen } from '../features/livechat/LiveChatScreen';
import { NotificationsScreen } from '../features/notifications/NotificationsScreen';
import { OwnerPortalScreen } from '../features/control/OwnerPortalScreen';
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
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`users-${authEpoch}`} active={name === 'users'}>
        <UsersScreen
          onRequestLogin={() => {
            setResumeArea('users');
            setScreen({ name: 'login' });
          }}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`dashboard-${authEpoch}`} active={name === 'dashboard'}>
        <DashboardScreen
          onNavigate={(target) => setScreen(screenForDashboardTarget(target))}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`billing-${authEpoch}`} active={name === 'billing'}>
        <BillingScreen />
      </KeepMountedPane>
      <KeepMountedPane key={`livechat-${authEpoch}`} active={name === 'livechat'}>
        <LiveChatScreen initialOpen={name === 'livechat' ? (screen.open ?? null) : null} />
      </KeepMountedPane>
      <KeepMountedPane key={`notifications-${authEpoch}`} active={name === 'notifications'}>
        <NotificationsScreen
          isAuthenticated={hasAccess}
          onDismissGate={() => {
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
          onOpenSection={(section) => setScreen({ name: 'cm_section', section, backTo: 'cm' })}
          onContinueSetup={(prompt) => {
            queueSetupHandoff({ text: prompt, mode: 'work', autoSend: true });
            setScreen({ name: 'chat' });
          }}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`faq-${authEpoch}`} active={name === 'faq'}>
        <FaqRoute
          onGoChat={() => setScreen({ name: 'chat' })}
          proposalReview={name === 'faq' ? (screen.proposalReview ?? null) : null}
        />
      </KeepMountedPane>
      <KeepMountedPane key={`owner-${authEpoch}`} active={name === 'owner'}>
        <OwnerPortalScreen />
      </KeepMountedPane>

      {name === 'cm_section' ? (
        <CmSectionScreen section={screen.section} proposalReview={screen.proposalReview ?? null} />
      ) : null}
      {name === 'resource' ? (
        <SimpleResourceScreen title={screen.title} path={screen.path} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
