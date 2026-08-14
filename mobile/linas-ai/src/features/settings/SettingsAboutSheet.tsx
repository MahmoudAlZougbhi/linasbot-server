import { Platform } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import {
  SETTINGS_ICONS,
  SettingsRow,
  SettingsSection,
  SettingsSheet,
} from './SettingsChrome';

type Props = {
  visible: boolean;
  appleBusy: boolean;
  onClose: () => void;
  onOpenAiLimits?: () => void;
  onOpenBusinessProfile: () => void;
  onLinkApple: () => void;
  onUnlinkApple: () => void;
};

/** About sheet keeps Apple / AI Limits / business profile reachable without cluttering the handoff list. */
export function SettingsAboutSheet({
  visible,
  appleBusy,
  onClose,
  onOpenAiLimits,
  onOpenBusinessProfile,
  onLinkApple,
  onUnlinkApple,
}: Props) {
  const { tr } = useI18n();
  const showApple = Platform.OS === 'ios';

  return (
    <SettingsSheet visible={visible} title={tr('settingsAboutLinas')} onClose={onClose}>
      <SettingsSection title={tr('settingsAiSection')}>
        {onOpenAiLimits ? (
          <SettingsRow
            icon={SETTINGS_ICONS.appearance}
            label={tr('settingsAiLimits')}
            hint={tr('settingsAiLimitsSub')}
            onPress={() => {
              onClose();
              onOpenAiLimits();
            }}
          />
        ) : null}
        <SettingsRow
          icon={SETTINGS_ICONS.about}
          label={tr('settingsBusinessProfile')}
          hint={tr('settingsBusinessProfileNote')}
          onPress={() => {
            onClose();
            onOpenBusinessProfile();
          }}
          last={!showApple}
        />
        {showApple ? (
          <>
            <SettingsRow
              icon={SETTINGS_ICONS.about}
              label={tr('settingsLinkApple')}
              hint={tr('settingsLinkAppleSub')}
              onPress={appleBusy ? undefined : onLinkApple}
            />
            <SettingsRow
              icon={SETTINGS_ICONS.about}
              label={tr('settingsUnlinkApple')}
              hint={tr('settingsUnlinkAppleSub')}
              onPress={appleBusy ? undefined : onUnlinkApple}
              last
            />
          </>
        ) : null}
      </SettingsSection>
    </SettingsSheet>
  );
}
