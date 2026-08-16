import { useState } from 'react';
import { ActivityIndicator, Alert, Linking, Pressable, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { AppModal } from '../../../../components/AppModal';
import { ModalScrim } from '../../../../components/ModalScrim';
import { TextField } from '../../../../components/TextField';
import { useI18n } from '../../../../i18n/LanguageContext';
import {
  pickDocumentAttachment,
  pickImageAttachment,
  pickVideoAttachment,
} from '../../../chat/v2/pickAttachment';
import { uploadCmArticleMedia } from '../../cmMediaApi';
import {
  asBranchAttachments,
  hrefForOpen,
  newLinkAttachment,
  type BranchAttachment,
} from './branchMedia';
import { locStyles, locTeal } from './locationHoursStyles';

type Props = {
  mapsUrl: string;
  attachments: unknown;
  onMapsUrl: (url: string) => void;
  onAttachments: (next: BranchAttachment[]) => void;
};

export function BranchMediaSection({ mapsUrl, attachments, onMapsUrl, onAttachments }: Props) {
  const { tr } = useI18n();
  const rows = asBranchAttachments(attachments);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [linkTitle, setLinkTitle] = useState('');

  const attachPicked = async (picked: { uri: string; name: string; mimeType: string } | null, kindHint?: string) => {
    if (!picked) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadCmArticleMedia(picked);
      const kind =
        uploaded.kind === 'image' || uploaded.kind === 'video'
          ? uploaded.kind
          : kindHint === 'video'
            ? 'video'
            : 'file';
      onAttachments([
        ...rows,
        {
          id: uploaded.media_id,
          kind,
          caption: '',
          mime: uploaded.mime || picked.mimeType,
          filename: uploaded.filename || picked.name,
          size: uploaded.size || 0,
          url: '',
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('aiSetupLocUploadFailed'));
    } finally {
      setUploading(false);
    }
  };

  const openMenu = (row: BranchAttachment | { kind: 'map'; filename: string; url: string }) => {
    const buttons: { text: string; style?: 'cancel' | 'destructive'; onPress?: () => void }[] = [];
    const href = row.kind === 'map' || row.kind === 'link' ? hrefForOpen(row.url) : '';
    if (href) {
      buttons.push({
        text: tr('aiSetupLocOpenLink'),
        onPress: () => void Linking.openURL(href),
      });
    }
    buttons.push({
      text: tr('aiSetupLocRemove'),
      style: 'destructive',
      onPress: () => {
        if (row.kind === 'map') onMapsUrl('');
        else onAttachments(rows.filter((item) => item.id !== row.id));
      },
    });
    buttons.push({ text: tr('aiSetupLocCancel'), style: 'cancel' });
    Alert.alert(row.filename || tr('aiSetupLocMediaTitle'), undefined, buttons);
  };

  const mapTrim = mapsUrl.trim();

  return (
    <View>
      <Text style={locStyles.sectionTitle}>{tr('aiSetupLocMediaTitle')}</Text>
      <Text style={locStyles.sectionHint}>{tr('aiSetupLocMediaHint')}</Text>
      <View style={locStyles.mediaActions}>
        <MediaAction
          icon="image"
          label={tr('aiSetupLocMediaImage')}
          onPress={() => void pickImageAttachment().then((f) => attachPicked(f, 'image'))}
        />
        <MediaAction
          icon="video"
          label={tr('aiSetupLocMediaVideo')}
          onPress={() => void pickVideoAttachment().then((f) => attachPicked(f, 'video'))}
        />
        <MediaAction
          icon="file"
          label={tr('aiSetupLocMediaFile')}
          onPress={() => void pickDocumentAttachment().then((f) => attachPicked(f, 'file'))}
        />
        <MediaAction icon="link" label={tr('aiSetupLocMediaLink')} onPress={() => setLinkOpen(true)} />
      </View>
      {uploading ? <ActivityIndicator color={locTeal} style={{ marginBottom: 8 }} /> : null}
      {error ? <Text style={locStyles.error}>{error}</Text> : null}
      {mapTrim ? (
        <MediaRow
          icon="map-pin"
          name={mapTrim.replace(/^https?:\/\//i, '')}
          kind={tr('aiSetupLocMapLinkType')}
          onMenu={() => openMenu({ kind: 'map', filename: mapTrim, url: mapTrim })}
        />
      ) : null}
      {rows.map((row) => (
        <MediaRow
          key={row.id}
          icon={row.kind === 'link' ? 'link' : row.kind === 'video' ? 'video' : row.kind === 'image' ? 'image' : 'file'}
          name={row.filename || row.url || row.id}
          kind={
            row.kind === 'image'
              ? tr('aiSetupLocMediaImage')
              : row.kind === 'video'
                ? tr('aiSetupLocMediaVideo')
                : row.kind === 'link'
                  ? tr('aiSetupLocMediaLink')
                  : tr('aiSetupLocMediaFile')
          }
          onMenu={() => openMenu(row)}
        />
      ))}
      <AppModal visible={linkOpen} onRequestClose={() => setLinkOpen(false)}>
        <ModalScrim onPress={() => setLinkOpen(false)} justify="center">
          <Pressable style={[locStyles.sheet, { marginHorizontal: 16 }]} onPress={(e) => e.stopPropagation()}>
            <Text style={locStyles.sheetTitle}>{tr('aiSetupLocAddLink')}</Text>
            <Text style={locStyles.fieldLabel}>{tr('aiSetupLocLinkTitle')}</Text>
            <TextField value={linkTitle} onChangeText={setLinkTitle} />
            <Text style={locStyles.fieldLabel}>{tr('aiSetupLocLinkUrl')}</Text>
            <TextField
              value={linkUrl}
              onChangeText={setLinkUrl}
              autoCapitalize="none"
              placeholder="https://"
            />
            <Pressable
              style={locStyles.saveBtn}
              onPress={() => {
                if (!linkUrl.trim()) {
                  setError(tr('aiSetupLocLinkRequired'));
                  return;
                }
                onAttachments([...rows, newLinkAttachment(hrefForOpen(linkUrl), linkTitle)]);
                setLinkUrl('');
                setLinkTitle('');
                setLinkOpen(false);
                setError(null);
              }}
            >
              <Text style={locStyles.saveText}>{tr('aiSetupLocAddLink')}</Text>
            </Pressable>
          </Pressable>
        </ModalScrim>
      </AppModal>
    </View>
  );
}

function MediaAction({
  icon,
  label,
  onPress,
}: {
  icon: 'image' | 'video' | 'file' | 'link';
  label: string;
  onPress: () => void;
}) {
  const name = icon === 'file' ? 'file-text' : icon;
  return (
    <Pressable style={locStyles.mediaAction} onPress={onPress} accessibilityRole="button">
      <View style={locStyles.mediaThumb}>
        <AppIcon icon={feather(name)} size={18} color={locTeal} />
      </View>
      <Text style={locStyles.mediaActionLabel}>{label}</Text>
    </Pressable>
  );
}

function MediaRow({
  icon,
  name,
  kind,
  onMenu,
}: {
  icon: 'image' | 'video' | 'file' | 'link' | 'map-pin';
  name: string;
  kind: string;
  onMenu: () => void;
}) {
  return (
    <View style={locStyles.mediaItem}>
      <View style={locStyles.mediaThumb}>
        <AppIcon icon={feather(icon === 'file' ? 'file-text' : icon)} size={16} color={locTeal} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={locStyles.mediaName} numberOfLines={1}>
          {name}
        </Text>
        <Text style={locStyles.mediaKind}>{kind}</Text>
      </View>
      <Pressable onPress={onMenu} hitSlop={8} accessibilityRole="button">
        <AppIcon icon={feather('more-horizontal')} size={18} color="#8A9A98" />
      </Pressable>
    </View>
  );
}
