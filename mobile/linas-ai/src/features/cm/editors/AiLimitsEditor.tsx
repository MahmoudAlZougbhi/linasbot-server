import { Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import type { StringKey } from '../../../i18n/locales/en';
import { AiLimitsPencilField } from './AiLimitsPencilField';
import { aiLimitsStyles } from './aiLimitsStyles';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  onSave?: () => void;
  saving?: boolean;
  dirty?: boolean;
  canSave?: boolean;
};

const DEFAULTS: Record<string, number> = {
  text_words_per_message: 500,
  text_replies_per_day: 20,
  text_replies_per_week: 100,
  text_replies_per_month: 300,
  photos_per_message: 2,
  image_per_day: 5,
  image_per_week: 20,
  image_per_month: 60,
  voice_minutes_per_message: 2,
  voice_minutes_per_day: 10,
  voice_minutes_per_week: 40,
  voice_minutes_per_month: 120,
};

function num(payload: Record<string, unknown>, key: string): string {
  const fallback = DEFAULTS[key] ?? 0;
  const raw = payload[key];
  if (raw === undefined || raw === null || raw === '') return String(fallback);
  const n = Number(raw);
  return String(Number.isFinite(n) ? n : fallback);
}

export function AiLimitsEditor({ payload, onChange, onSave, saving, dirty, canSave }: Props) {
  const { tr } = useI18n();
  const setNum = (key: string, value: string) => {
    const n = Number(value.replace(/[^\d]/g, ''));
    onChange({ ...payload, [key]: Number.isFinite(n) ? n : 0 });
  };

  return (
    <View>
      <View style={aiLimitsStyles.banner}>
        <AppIcon icon={feather('users')} size={18} color="#1F6B63" />
        <Text style={aiLimitsStyles.bannerText}>{tr('aiLimitsBanner')}</Text>
      </View>

      <LimitCard
        icon="message-circle"
        title={tr('aiLimitsTextChat')}
        rowLabel={tr('aiLimitsReadPerMessage')}
        rowKey="text_words_per_message"
        rowSuffix={tr('aiLimitsWordsSuffix')}
        periodLabel={tr('aiLimitsRepliesPerCustomer')}
        dayKey="text_replies_per_day"
        weekKey="text_replies_per_week"
        monthKey="text_replies_per_month"
        payload={payload}
        setNum={setNum}
        tr={tr}
      />
      <LimitCard
        icon="image"
        title={tr('aiLimitsPhotos')}
        rowLabel={tr('aiLimitsPhotosPerMessage')}
        rowKey="photos_per_message"
        periodLabel={tr('aiLimitsAnalysesPerCustomer')}
        dayKey="image_per_day"
        weekKey="image_per_week"
        monthKey="image_per_month"
        payload={payload}
        setNum={setNum}
        tr={tr}
      />
      <LimitCard
        icon="mic"
        title={tr('aiLimitsVoice')}
        rowLabel={tr('aiLimitsMinutesPerMessage')}
        rowKey="voice_minutes_per_message"
        rowSuffix={tr('aiLimitsMinSuffix')}
        periodLabel={tr('aiLimitsMinutesPerCustomer')}
        dayKey="voice_minutes_per_day"
        weekKey="voice_minutes_per_week"
        monthKey="voice_minutes_per_month"
        payload={payload}
        setNum={setNum}
        tr={tr}
      />

      <View style={aiLimitsStyles.infoBanner}>
        <AppIcon icon={feather('info')} size={18} color="#1F6B63" />
        <View style={{ flex: 1 }}>
          <Text style={aiLimitsStyles.infoTitle}>{tr('aiLimitsAutoTitle')}</Text>
          <Text style={aiLimitsStyles.infoBody}>{tr('aiLimitsAutoBody')}</Text>
          <Text style={aiLimitsStyles.infoBody}>{tr('aiLimitsAutoBody2')}</Text>
        </View>
      </View>

      {onSave ? (
        <>
          <PrimaryButton
            label={tr('aiLimitsSave')}
            onPress={onSave}
            loading={saving}
            disabled={!dirty || !canSave}
          />
          <Text style={aiLimitsStyles.applyHint}>{tr('aiLimitsApplyNow')}</Text>
        </>
      ) : null}
    </View>
  );
}

function LimitCard({
  icon,
  title,
  rowLabel,
  rowKey,
  rowSuffix,
  periodLabel,
  dayKey,
  weekKey,
  monthKey,
  payload,
  setNum,
  tr,
}: {
  icon: 'message-circle' | 'image' | 'mic';
  title: string;
  rowLabel: string;
  rowKey: string;
  rowSuffix?: string;
  periodLabel: string;
  dayKey: string;
  weekKey: string;
  monthKey: string;
  payload: Record<string, unknown>;
  setNum: (key: string, value: string) => void;
  tr: (key: StringKey) => string;
}) {
  return (
    <View style={aiLimitsStyles.card}>
      <View style={aiLimitsStyles.cardHeader}>
        <AppIcon icon={feather(icon)} size={20} color="#008B8B" />
        <Text style={aiLimitsStyles.cardTitle}>{title}</Text>
      </View>
      <View style={aiLimitsStyles.row}>
        <Text style={aiLimitsStyles.rowLabel}>{rowLabel}</Text>
        <AiLimitsPencilField
          value={num(payload, rowKey)}
          onChange={(v) => setNum(rowKey, v)}
          suffix={rowSuffix}
          style={aiLimitsStyles.fieldWide}
        />
      </View>
      <Text style={aiLimitsStyles.periodLabel}>{periodLabel}</Text>
      <View style={aiLimitsStyles.periodRow}>
        {(
          [
            [dayKey, 'aiLimitsDay'],
            [weekKey, 'aiLimitsWeek'],
            [monthKey, 'aiLimitsMonth'],
          ] as const
        ).map(([key, caption]) => (
          <View key={key} style={aiLimitsStyles.periodCol}>
            <Text style={aiLimitsStyles.periodCaption}>{tr(caption)}</Text>
            <AiLimitsPencilField value={num(payload, key)} onChange={(v) => setNum(key, v)} />
          </View>
        ))}
      </View>
    </View>
  );
}
