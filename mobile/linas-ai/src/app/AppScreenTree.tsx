import { StyleSheet, View } from 'react-native';

import { LoginScreen } from '../features/auth/LoginScreen';
import { RegisterScreen } from '../features/auth/RegisterScreen';
import { ForgotPasswordScreen } from '../features/auth/ForgotPasswordScreen';
import { BillingScreen } from '../features/billing/BillingScreen';
import { SubscriptionGateScreen } from '../features/billing/SubscriptionGateScreen';
import { ChatScreen } from '../features/chat/ChatScreen';
import { queueSetupHandoff } from '../features/chat/pendingSetupHandoff';
import { CmScreen } from '../features/cm/CmScreen';
import { CmSectionScreen } from '../features/cm/CmSectionScreen';
import { AddProductScreen } from '../features/products/AddProductScreen';
import { ProductDetailsScreen } from '../features/products/ProductDetailsScreen';
import { ProductsImportScreen } from '../features/products/ProductsImportScreen';
import { ProductsScreen } from '../features/products/ProductsScreen';
import { ServicesScreen } from '../features/services/ServicesScreen';
import type { CmProposalReview } from '../features/cm/cmProposalReview';
import type { ControlArea } from '../features/control/controlAreas';
import { DashboardScreen } from '../features/dashboard/DashboardScreen';
import { screenForDashboardTarget } from '../features/dashboard/dashboardNavigation';
import { FaqRoute } from '../features/faq/FaqRoute';
import { IntegrationsScreen } from '../features/integrations/IntegrationsScreen';
import { LiveChatScreen } from '../features/livechat/LiveChatScreen';
import { NotificationsScreen } from '../features/notifications/NotificationsScreen';
import { RequestsScreen } from '../features/requests/RequestsScreen';
import { OwnerPortalScreen } from '../features/control/OwnerPortalScreen';
import { SettingsScreen } from '../features/settings/SettingsScreen';
import { SmartFollowUpScreen } from '../features/smartFollowUp/SmartFollowUpScreen';
import { SimpleResourceScreen } from '../features/shared/SimpleResourceScreen';
import { UsersScreen } from '../features/users/UsersScreen';
import { EphemeralRoute } from './EphemeralRoute';
import { isKeepMountedScreen } from './keepMountedPolicy';
import { ModulePane } from './ModulePane';
import type { Screen } from './navigation';

type Props = {
  screen: Screen;
  authEpoch: number;
  hasAccess: boolean;
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
          onForgotPassword={() => setScreen({ name: 'forgot_password' })}
          onBack={() => setScreen({ name: 'chat' })}
        />
      ) : null}
      {name === 'register' ? (
        <RegisterScreen
          onBack={() => setScreen({ name: 'login' })}
          onLoggedIn={() => void afterLogin()}
        />
      ) : null}
      {name === 'forgot_password' ? (
        <ForgotPasswordScreen
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

      <ModulePane keep={isKeepMountedScreen('chat')} name="chat" active={chatActive} authEpoch={authEpoch}>
        <ChatScreen
          isAuthenticated={hasAccess}
          onOpenArea={onOpenArea}
          onOpenCmReview={onOpenCmReview}
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('settings')} name="settings" active={name === 'settings'} authEpoch={authEpoch}>
        <SettingsScreen
          onLogout={() => void logout()}
          onOpenNotifications={() => setScreen({ name: 'notifications', backTo: 'settings' })}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('integrations')} name="integrations" active={name === 'integrations'} authEpoch={authEpoch}>
        <IntegrationsScreen
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('users')} name="users" active={name === 'users'} authEpoch={authEpoch}>
        <UsersScreen
          onRequestLogin={() => {
            setResumeArea('users');
            setScreen({ name: 'login' });
          }}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('dashboard')} name="dashboard" active={name === 'dashboard'} authEpoch={authEpoch}>
        <DashboardScreen
          active={name === 'dashboard'}
          onNavigate={(target) => setScreen(screenForDashboardTarget(target))}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('billing')} name="billing" active={name === 'billing'} authEpoch={authEpoch}>
        <BillingScreen
          openChoosePlan={name === 'billing' && 'browsePlans' in screen && screen.browsePlans === true}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('livechat')} name="livechat" active={name === 'livechat'} authEpoch={authEpoch}>
        <LiveChatScreen
          active={name === 'livechat'}
          initialOpen={name === 'livechat' ? (screen.open ?? null) : null}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('requests')} name="requests" active={name === 'requests'} authEpoch={authEpoch}>
        <RequestsScreen
          onOpenLiveChat={(target) => setScreen({ name: 'livechat', open: target })}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('notifications')} name="notifications" active={name === 'notifications'} authEpoch={authEpoch}>
        <NotificationsScreen
          isAuthenticated={hasAccess}
          sectionTitle={name === 'notifications' && screen.backTo === 'settings'}
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
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('cm')} name="cm" active={name === 'cm'} authEpoch={authEpoch}>
        <CmScreen
          onOpenSection={(section) => {
            if (section === 'prices') {
              setScreen({ name: 'services', backTo: 'cm' });
              return;
            }
            if (section === 'dynamic_messages') {
              setScreen({ name: 'cm_section', section: 'ai_basics', backTo: 'cm' });
              return;
            }
            if (section === 'services') {
              setScreen({ name: 'services', backTo: 'cm' });
              return;
            }
            setScreen({ name: 'cm_section', section, backTo: 'cm' });
          }}
          onOpenProducts={() => setScreen({ name: 'products', backTo: 'cm' })}
          onContinueSetup={(prompt) => {
            queueSetupHandoff({ text: prompt, mode: 'work', autoSend: true });
            setScreen({ name: 'chat' });
          }}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('faq')} name="faq" active={name === 'faq'} authEpoch={authEpoch}>
        <FaqRoute
          onGoChat={() => setScreen({ name: 'chat' })}
          proposalReview={name === 'faq' ? (screen.proposalReview ?? null) : null}
        />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('smartFollowUp')} name="smartFollowUp" active={name === 'smartFollowUp'} authEpoch={authEpoch}>
        <SmartFollowUpScreen />
      </ModulePane>
      <ModulePane keep={isKeepMountedScreen('owner')} name="owner" active={name === 'owner'} authEpoch={authEpoch}>
        <OwnerPortalScreen />
      </ModulePane>

      {name === 'products' ? (
        <EphemeralRoute>
          <ProductsScreen
            onBack={screen.backTo === 'cm' ? () => setScreen({ name: 'cm' }) : undefined}
            onAdd={() => setScreen({ name: 'products_add', backTo: 'products' })}
            onImport={() => setScreen({ name: 'products_import', backTo: 'products' })}
            onOpenDetails={(productId) =>
              setScreen({ name: 'products_details', productId, backTo: 'products' })
            }
          />
        </EphemeralRoute>
      ) : null}
      {name === 'products_import' ? (
        <EphemeralRoute>
          <ProductsImportScreen
            onBack={() => setScreen({ name: 'products', backTo: 'cm' })}
            onImported={() => setScreen({ name: 'products', backTo: 'cm' })}
          />
        </EphemeralRoute>
      ) : null}
      {name === 'products_add' ? (
        <EphemeralRoute>
          <AddProductScreen
            onBack={() => setScreen({ name: 'products', backTo: 'cm' })}
            onSaved={() => setScreen({ name: 'products', backTo: 'cm' })}
          />
        </EphemeralRoute>
      ) : null}
      {name === 'products_details' ? (
        <EphemeralRoute>
          <ProductDetailsScreen
            productId={screen.productId}
            onBack={() => setScreen({ name: 'products', backTo: 'cm' })}
            onEdit={() =>
              setScreen({
                name: 'products_edit',
                productId: screen.productId,
                backTo: 'products_details',
              })
            }
            onDeleted={() => setScreen({ name: 'products', backTo: 'cm' })}
          />
        </EphemeralRoute>
      ) : null}
      {name === 'products_edit' ? (
        <EphemeralRoute>
          <AddProductScreen
            productId={screen.productId}
            onBack={() =>
              screen.backTo === 'products_details'
                ? setScreen({
                    name: 'products_details',
                    productId: screen.productId,
                    backTo: 'products',
                  })
                : setScreen({ name: 'products', backTo: 'cm' })
            }
            onSaved={() =>
              setScreen({
                name: 'products_details',
                productId: screen.productId,
                backTo: 'products',
              })
            }
          />
        </EphemeralRoute>
      ) : null}

      {name === 'services' ? (
        <EphemeralRoute>
          <ServicesScreen
            proposalReview={screen.proposalReview ?? null}
            onBack={
              screen.backTo === 'cm'
                ? () => setScreen({ name: 'cm' })
                : screen.backTo === 'chat'
                  ? () => setScreen({ name: 'chat' })
                  : undefined
            }
          />
        </EphemeralRoute>
      ) : null}

      {name === 'cm_section' ? (
        <EphemeralRoute>
          <CmSectionScreen
            section={screen.section}
            proposalReview={screen.proposalReview ?? null}
            onOpenLocations={() => setScreen({ name: 'cm_section', section: 'branches', backTo: 'cm' })}
            onBack={
              screen.backTo === 'settings'
                ? () => setScreen({ name: 'settings' })
                : screen.backTo === 'cm'
                  ? () => setScreen({ name: 'cm' })
                  : screen.backTo === 'chat'
                    ? () => setScreen({ name: 'chat' })
                    : undefined
            }
          />
        </EphemeralRoute>
      ) : null}
      {name === 'resource' ? (
        <EphemeralRoute>
          <SimpleResourceScreen title={screen.title} path={screen.path} />
        </EphemeralRoute>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
