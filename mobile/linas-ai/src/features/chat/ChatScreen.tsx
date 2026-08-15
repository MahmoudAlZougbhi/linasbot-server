import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  View,
} from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import type { ControlArea } from '../control/controlAreas';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { BuyCreditsSheet } from '../billing/BuyCreditsSheet';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatModeToggle } from './ChatModeToggle';
import { ChatScreenOverlays } from './ChatScreenOverlays';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStatusBanners } from './ChatStatusBanners';
import { CreditsPausedBanner } from './CreditsPausedBanner';
import { resolveOwnerModeForOutgoing } from './ownerChatMode';
import { PendingAttachmentsStrip } from './PendingAttachmentsStrip';
import { buildApproveSendOpts, buildDiscardSendOpts } from './proposalBarActions';
import { sendChatMessage } from './sendChatMessage';
import { chatErrorLabelKey, retryAssistantMessage } from './chatRetryHandlers';
import { usePendingChatNavHandoff } from './usePendingChatNavHandoff';
import { useSetupHandoff } from './useSetupHandoff';
import { useChatScreenController } from './useChatScreenController';
import { ChoiceChips } from './v2/ChoiceChips';

type Props = {
  isAuthenticated: boolean;
  onOpenArea: (area: ControlArea) => void;
  onOpenCmReview?: (review: CmProposalReview) => void;
  onRequestLogin: () => void;
  onRequestRegister: () => void;
};

export function ChatScreen({
  isAuthenticated,
  onOpenArea,
  onOpenCmReview,
  onRequestLogin,
  onRequestRegister,
}: Props) {
  const c = useChatScreenController(isAuthenticated, onRequestLogin);

  useSetupHandoff({
    isAuthenticated,
    loading: c.owner.loading,
    streaming: c.turn.streaming,
    setDraft: c.setDraft,
    setOwnerMode: c.setOwnerMode,
    send: (text, mode) => {
      c.stickToBottomRef.current = true;
      void c.turn.send(text, { owner_mode: mode });
    },
  });

  usePendingChatNavHandoff({
    isAuthenticated,
    owner: c.owner,
    turn: c.turn,
    setOwnerMode: c.setOwnerMode,
    stickToBottom: () => {
      c.stickToBottomRef.current = true;
    },
    afterOpen: () => c.armOpenAtLatest(),
  });

  return (
    <GradientBackground>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <View style={styles.flex}>
        {c.showModeToggle && !c.drawerOpen ? (
          <ChatModeToggle mode={c.ownerMode} onChange={c.setOwnerMode} />
        ) : null}

        <ChatStatusBanners
          offline={c.offline}
          errorLabel={c.error ? c.tr(chatErrorLabelKey(c.error)) : null}
          voiceError={c.voice.voiceError}
          onRetry={() => {
            c.setOffline(false);
            if (!isAuthenticated) {
              c.guest.setError(null);
              void c.guest.bootstrap();
              return;
            }
            const err = c.owner.error;
            c.owner.setError(null);
            if (err === 'messageFailed') return;
            void c.owner.bootstrap();
          }}
        />

        {c.loading ? (
          <View style={styles.center} accessibilityLabel="Loading conversation">
            <LinasLoadingIndicator variant="screen" />
          </View>
        ) : (
          <ChatMessageList
            listRef={c.listRef}
            listKey={c.listKey}
            messages={c.messages}
            isAuthenticated={isAuthenticated}
            stickToBottomRef={c.stickToBottomRef}
            scrollToBottom={c.scrollToBottom}
            followBottomIfStuck={c.followBottomIfStuck}
            imagePreviewByContent={c.imagePreviewByContent}
            thinking={c.turn.thinking || (!isAuthenticated && c.guest.sending)}
            thinkingLabel={c.tr('chatThinking')}
            statusRows={c.turn.statusRows}
            liveText={c.turn.liveText}
            cards={c.turn.cards}
            proposedPatch={isAuthenticated ? c.owner.proposedPatch : null}
            hasMore={isAuthenticated ? c.owner.hasMore : false}
            loadingMore={isAuthenticated ? c.owner.loadingMore : false}
            onLoadOlder={() => {
              if (isAuthenticated) void c.owner.loadOlder();
            }}
            onRetryAssistant={(content) =>
              retryAssistantMessage({
                isAuthenticated,
                streaming: c.turn.streaming,
                guestSending: c.guest.sending,
                guestGated: c.guest.gated,
                content,
                ownerSend: (text) => void c.ownerSendWithMode(text),
                guestSend: (text) => void c.guest.send(text),
                openAuth: () => c.openAuthPreservingDraft(true),
                scrollToBottom: c.scrollToBottom,
              })
            }
            onApproveDraft={(token, approveOpts) => {
              c.setReviseProposalId(null);
              void c.ownerSendWithMode('', buildApproveSendOpts(token, approveOpts));
            }}
            onDiscardProposal={(token) => {
              c.owner.setProposedPatch(null);
              c.owner.setPendingConfirm(null);
              c.setReviseProposalId(null);
              const d = buildDiscardSendOpts(token);
              if (d) void c.ownerSendWithMode('', d);
            }}
            onEditProposal={(id) => {
              c.setReviseProposalId(id);
              c.composerInputRef.current?.focus();
            }}
            onOpenCm={(r) => (r && onOpenCmReview ? onOpenCmReview(r) : onOpenArea('cm'))}
            onGuestPrompt={(prompt) => {
              if (c.guest.gated) {
                c.openAuthPreservingDraft(true);
                return;
              }
              c.scrollToBottom();
              void c.guest.send(prompt);
            }}
            showOwnerWelcomeChips={
              isAuthenticated && !c.hasUserMessage && !c.turn.liveText && !c.turn.streaming
            }
            onOwnerWelcomeChip={(chip) => {
              if (c.turn.creditsPaused) return;
              const mode = resolveOwnerModeForOutgoing(chip.mode, chip.prompt);
              c.setOwnerMode(mode);
              c.scrollToBottom();
              void c.turn.send(chip.prompt, { owner_mode: mode, reply_language: c.language });
            }}
            seedTypewriterMessageId={isAuthenticated ? c.owner.seedTypewriterMessageId : null}
            onSeedTypewriterDone={c.owner.clearSeedTypewriter}
          />
        )}

        {isAuthenticated ? (
          <ChoiceChips
            choices={c.turn.choices}
            disabled={c.choiceBusy || c.turn.streaming || Boolean(c.turn.creditsPaused)}
            onSelect={(choice) => {
              if (!c.turn.choiceSetId || c.choiceBusy) return;
              c.setChoiceBusy(true);
              c.scrollToBottom();
              void c.ownerSendWithMode(choice.label, {
                choice_id: choice.id,
                choice_set_id: c.turn.choiceSetId,
              }).finally(() => c.setChoiceBusy(false));
            }}
          />
        ) : null}

        <PendingAttachmentsStrip
          files={c.pendingFiles}
          onRemove={(id) => c.setPendingFiles((prev) => prev.filter((f) => f.id !== id))}
        />

        {isAuthenticated && c.turn.creditsPaused ? (
          <CreditsPausedBanner
            showUpgrade={c.turn.creditsPaused.showUpgrade}
            onBuyCredits={() => c.credits.setOpen(true)}
            onUpgrade={() => c.nav?.openChoosePlan()}
          />
        ) : null}

        <ChatComposer
          draft={c.draft}
          onChangeDraft={c.setDraft}
          sending={
            c.sending ||
            (!isAuthenticated && c.guest.gated) ||
            (isAuthenticated && !c.sessionReady) ||
            Boolean(c.turn.creditsPaused)
          }
          canSendWithAttachment={c.pendingFiles.length > 0}
          voiceState={c.authVoice?.voiceState ?? 'idle'}
          elapsedMs={c.authVoice?.elapsedMs ?? 0}
          metering={c.authVoice?.metering ?? null}
          inputRef={c.composerInputRef}
          showPlus={isAuthenticated}
          showMic={isAuthenticated}
          showModelChip={isAuthenticated}
          ownerMode={c.ownerMode}
          onOwnerModeChange={c.setOwnerMode}
          editChipActive={Boolean(c.reviseProposalId)}
          onClearEditChip={() => c.setReviseProposalId(null)}
          onPlus={() => c.setPlusOpen(true)}
          onToggleVoice={() => void c.voice.toggleVoice()}
          onResumeVoice={() => void c.voice.resumeVoice()}
          onConfirmVoice={() => void c.voice.confirmVoice()}
          onDiscardVoice={() => void c.voice.discardVoice()}
          onStop={c.turn.streaming ? () => c.turn.stop() : undefined}
          onSend={() =>
            void sendChatMessage({
              isAuthenticated,
              draft: c.draft,
              setDraft: c.setDraft,
              pendingFiles: c.pendingFiles,
              setPendingFiles: c.setPendingFiles,
              voiceState: c.voice.voiceState,
              conversationId: c.owner.conversationId,
              guestGated: c.guest.gated,
              guestSend: c.guest.send,
              ownerSend: c.ownerSendWithMode,
              appendOptimisticUser: c.owner.appendOptimisticUser,
              removeOptimisticUser: c.owner.removeOptimisticUser,
              autoTitleFromOutgoing: c.owner.autoTitleFromOutgoing,
              openAuthPreservingDraft: c.openAuthPreservingDraft,
              setOffline: c.setOffline,
              setSendError: (v) => (isAuthenticated ? c.owner.setError(v) : c.guest.setError(v)),
              scrollToBottom: c.scrollToBottom,
              imagePreviewByContent: c.imagePreviewByContent,
            })
          }
        />
        </View>
      </KeyboardAvoidingView>
      {!c.drawerOpen ? (
        <ChatHeader
          onOpenMenu={() => {
            Keyboard.dismiss();
            c.setDrawerOpen(true);
          }}
        />
      ) : null}

      <ChatScreenOverlays
        drawerOpen={c.drawerOpen}
        onCloseDrawer={() => c.setDrawerOpen(false)}
        isAuthenticated={isAuthenticated}
        activeArea="chat"
        history={c.owner.history}
        archivedIds={c.archivedIds}
        pinnedIds={c.pinnedIds}
        activeId={c.owner.conversationId}
        workspaceLabel={c.workspaceLabel}
        onOpenArea={onOpenArea}
        onNewChat={() => { c.setDrawerOpen(false); c.startNewChat(); }}
        onOpenChat={(id) => {
          c.stickToBottomRef.current = true;
          void c.owner.openConversation(id).then(() => c.armOpenAtLatest());
        }}
        onTogglePin={(id) => void c.togglePin(id)}
        onArchive={(id) => void c.owner.setArchived(id, true)}
        onUnarchive={(id) => void c.owner.setArchived(id, false)}
        onRename={(id, title) => void c.owner.renameConversation(id, title)}
        onDelete={(id) => void c.owner.deleteConversation(id)}
        onLogin={c.goToLoginPreservingDraft}
        onRegister={onRequestRegister}
        plusOpen={c.plusOpen}
        onClosePlus={() => c.setPlusOpen(false)}
        pendingFiles={c.pendingFiles}
        setPendingFiles={c.setPendingFiles}
        authGate={c.authGate}
        hardLimit={c.hardLimit}
        guestGated={c.guest.gated}
        gateText={c.guest.gateText}
        onCloseAuth={() => { c.setAuthGate(false); c.setHardLimit(false); }}
        onRequestLogin={onRequestLogin}
        onRequestRegister={onRequestRegister}
      />
      <BuyCreditsSheet
        visible={c.credits.open}
        prices={c.credits.prices}
        purchasing={c.credits.purchasing}
        locale={c.credits.locale}
        tr={c.credits.tr}
        onClose={() => c.credits.setOpen(false)}
        onBuy={(pack) => void c.credits.buy(pack)}
      />
    </GradientBackground>
  );
}
