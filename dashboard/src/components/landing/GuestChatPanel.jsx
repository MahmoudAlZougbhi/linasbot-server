import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ensureGuestSession,
  getOrCreateGuestSessionId,
  sendGuestMessage,
} from '../../utils/guestChatApi';
import StoreBadges from './StoreBadges';
import LinasStar from './LinasStar';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';

const GATE_FALLBACK = {
  en: 'You’ve reached the guest limit. Download the Linas AI app and subscribe to continue.',
  ar: 'وصلت إلى حد الضيف. حمّل تطبيق Linas AI واشترك للمتابعة.',
  fr: 'Limite invité atteinte. Téléchargez l’app Linas AI et abonnez-vous pour continuer.',
};

const COPY = {
  en: {
    title: 'Talk to Linas',
    subtitle: 'Ask about Linas AI — product help only.',
    placeholder: 'Message Linas',
    send: 'Send',
    inputTooLarge: 'What you sent is too large. Subscribe to Linas AI to continue with larger messages.',
    mediaBlocked: 'Guests can’t send photos or files. Subscribe to use attachments.',
    retry: 'Couldn’t start guest chat. Try again.',
    failed: 'Message failed. Please try again.',
    unavailable: 'Linas AI is temporarily unavailable. Please try again in a moment.',
    continueInApp: 'Continue in the app',
    greeting: 'Hi — I’m Linas AI. Ask how the product handles DMs, comments, setup, or account access.',
    chips: ['What can Linas answer?', 'How are replies controlled?', 'How does Meta setup work?'],
    thinking: 'Thinking…',
  },
  ar: {
    title: 'تحدّث مع Linas',
    subtitle: 'اسأل عن Linas AI — شرح المنتج فقط.',
    placeholder: 'راسل Linas',
    send: 'إرسال',
    inputTooLarge: 'اللي بعثتو كبير زيادة. اشترك بـ Linas AI لتقدر تبعت رسائل أطول.',
    mediaBlocked: 'الضيوف ما بيقدروا يبعتوا صور أو ملفات. اشترك لاستخدام المرفقات.',
    retry: 'تعذّر بدء الدردشة. حاول مجدداً.',
    failed: 'فشل الإرسال. حاول مجدداً.',
    unavailable: 'Linas AI غير متاح مؤقتاً. حاول مرة أخرى بعد لحظات.',
    continueInApp: 'تابع في التطبيق',
    greeting: 'مرحباً — أنا Linas AI. اسأل عن الرسائل والتعليقات والإعداد.',
    chips: ['ماذا يجيب Linas؟', 'كيف تُضبط الردود؟', 'كيف يعمل إعداد Meta؟'],
    thinking: 'يفكّر…',
  },
  fr: {
    title: 'Parler à Linas',
    subtitle: 'Questions sur Linas AI — produit uniquement.',
    placeholder: 'Message Linas',
    send: 'Envoyer',
    inputTooLarge: 'Votre message est trop volumineux. Abonnez-vous à Linas AI pour envoyer des messages plus longs.',
    mediaBlocked: 'Les invités ne peuvent pas envoyer de photos ou de fichiers. Abonnez-vous pour les pièces jointes.',
    retry: 'Impossible de démarrer le chat. Réessayez.',
    failed: 'Échec de l’envoi. Réessayez.',
    unavailable: 'Linas AI est temporairement indisponible. Réessayez dans un instant.',
    continueInApp: 'Continuer dans l’app',
    greeting: 'Bonjour — je suis Linas AI. Demandez pour les DMs, commentaires ou configuration.',
    chips: ['Que peut répondre Linas ?', 'Comment sont contrôlées les réponses ?', 'Comment marche Meta ?'],
    thinking: 'Réflexion…',
  },
};

/**
 * Guest AI floating widget — same product chat feel as the app, without limit meters.
 * @param {{ open: boolean, onOpen: () => void, onClose: () => void, showFab?: boolean }} props
 */
export default function GuestChatPanel({ open = false, onOpen = () => {}, onClose = () => {}, showFab = true }) {
  const { locale } = usePublicLandingLocale();
  const copy = COPY[locale] || COPY.en;
  const dir = locale === 'ar' ? 'rtl' : 'ltr';

  const [guestId, setGuestId] = useState(/** @type {string | null} */ (null));
  const [messages, setMessages] = useState(/** @type {Array<{id: string; role: string; content: string}>} */ ([]));
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(/** @type {string | null} */ (null));
  const [gated, setGated] = useState(false);
  const [gateText, setGateText] = useState(/** @type {string | null} */ (null));
  const listRef = useRef(/** @type {HTMLDivElement | null} */ (null));

  const bootstrap = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const id = getOrCreateGuestSessionId();
      setGuestId(id);
      const session = await ensureGuestSession(id, locale);
      setMessages(session.messages || []);
      setGated(Boolean(session.limit_reached));
      if (session.limit_reached) {
        setGateText(GATE_FALLBACK[locale] || GATE_FALLBACK.en);
      }
    } catch {
      setError(copy.retry);
    } finally {
      setLoading(false);
    }
  }, [copy.retry, locale]);

  useEffect(() => {
    if (!open) return;
    void bootstrap();
  }, [bootstrap, open]);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, gated, sending, open]);

  /** @param {string} content */
  const sendContent = async (content) => {
    if (!guestId || gated || sending) return;
    const trimmed = content.trim();
    if (!trimmed) return;
    setSending(true);
    setError(null);
    setDraft('');
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'user', content: trimmed }]);
    try {
      const result = await sendGuestMessage(guestId, trimmed, locale);
      if (!result.ok) {
        setGated(true);
        setGateText(
          result.gateMessages?.[locale] || result.gateMessages?.en || GATE_FALLBACK[locale] || GATE_FALLBACK.en,
        );
        setMessages(result.session.messages || []);
        return;
      }
      setMessages(result.session.messages || []);
      if (result.session.limit_reached) {
        setGated(true);
        setGateText(GATE_FALLBACK[locale] || GATE_FALLBACK.en);
      }
    } catch (err) {
      const code =
        err && typeof err === 'object' && 'code' in err
          ? String(/** @type {{code?: string}} */ (err).code || '')
          : err instanceof Error
            ? err.message
            : '';
      const status =
        err && typeof err === 'object' && 'status' in err ? Number(/** @type {{status?: number}} */ (err).status) : 0;
      if (code === 'GUEST_INPUT_TOO_LARGE' || code === 'input_token_limit') {
        setError(copy.inputTooLarge);
      } else if (code === 'GUEST_MEDIA_BLOCKED' || code === 'guest_media_blocked') {
        setError(copy.mediaBlocked);
      } else if (status === 503) {
        setError(copy.unavailable);
      } else {
        setError(copy.failed);
      }
      try {
        const session = await ensureGuestSession(guestId, locale);
        setMessages(session.messages || []);
        setGated(Boolean(session.limit_reached));
      } catch {
        setMessages((prev) => prev.filter((m) => !String(m.id).startsWith('local-')));
      }
    } finally {
      setSending(false);
    }
  };

  /** @param {import('react').FormEvent<HTMLFormElement>} event */
  const onSend = async (event) => {
    event.preventDefault();
    await sendContent(draft);
  };

  return (
    <div id="talk-to-linas" className="scroll-mt-24">
      {open && (
        <div
          className="fixed bottom-24 right-4 z-40 flex w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-[#E4E8E6] bg-white shadow-[0_24px_80px_rgba(11,13,12,0.28)] sm:right-6"
          role="dialog"
          aria-label={copy.title}
          dir={dir}
        >
          <div className="flex items-center justify-between border-b border-[#E4E8E6] px-4 py-3">
            <div className="flex items-center gap-2.5">
              <LinasStar className="h-5 w-5" />
              <div>
                <p className="text-sm font-semibold text-[#171A19]">Linas AI</p>
                <p className="text-[0.7rem] text-[#8A938F]">{copy.subtitle}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-2 py-1 text-lg text-[#8A938F] hover:bg-[#F0F3F1] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
              aria-label="Close guest chat"
            >
              ×
            </button>
          </div>

          <div
            ref={listRef}
            className="flex max-h-[min(22rem,45vh)] min-h-[14rem] flex-col gap-3 overflow-y-auto px-4 py-4"
            role="log"
            aria-live="polite"
          >
            {loading && <p className="text-sm text-[#5C6663]">Connecting to Linas…</p>}
            {!loading && messages.length === 0 && (
              <div className="rounded-2xl bg-[#F0F3F1] px-3.5 py-2.5 text-sm leading-relaxed text-[#171A19]">
                {copy.greeting}
              </div>
            )}
            {!loading &&
              messages.map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[90%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                        isUser ? 'bg-[#06715F] text-white' : 'bg-[#F0F3F1] text-[#171A19]'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                );
              })}
            {!loading && sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-[#F0F3F1] px-3.5 py-2.5 text-sm text-[#5C6663]">{copy.thinking}</div>
              </div>
            )}
            {!loading && !gated && messages.length <= 1 && !sending && (
              <div className="flex flex-col gap-2">
                {copy.chips.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    disabled={sending}
                    onClick={() => void sendContent(chip)}
                    className="flex items-center justify-between rounded-xl border border-[#E4E8E6] bg-white px-3 py-2.5 text-left text-sm font-medium text-[#171A19] hover:border-[#06715F]/35 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
                  >
                    {chip}
                    <span aria-hidden="true">→</span>
                  </button>
                ))}
              </div>
            )}
            {gated && gateText && (
              <div className="rounded-2xl border border-[#D5DCD8] bg-[#F6F7F6] p-4 text-sm text-[#171A19]">
                <p className="font-semibold">{gateText}</p>
                <p className="mt-3 text-xs font-medium uppercase tracking-wide text-[#5C6663]">{copy.continueInApp}</p>
                <div className="mt-3">
                  <StoreBadges compact />
                </div>
              </div>
            )}
          </div>

          {error && (
            <p className="border-t border-[#E4E8E6] px-4 py-2 text-sm text-[#DC2626]" role="alert">
              {error}
            </p>
          )}

          <form onSubmit={onSend} className="flex items-center gap-2 border-t border-[#E4E8E6] p-3">
            <label className="sr-only" htmlFor="guest-chat-input">
              {copy.placeholder}
            </label>
            <input
              id="guest-chat-input"
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={loading || gated || sending}
              placeholder={copy.placeholder}
              className="min-w-0 flex-1 rounded-full border border-[#E4E8E6] bg-white px-4 py-2.5 text-sm text-[#171A19] placeholder:text-[#8A938F] focus:border-[#06715F] focus:outline-none focus:ring-2 focus:ring-[#06715F]/25 disabled:opacity-60"
              maxLength={2000}
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={loading || gated || sending || !draft.trim()}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-[#06715F] text-white disabled:cursor-not-allowed disabled:opacity-50"
              aria-label={copy.send}
            >
              {sending ? '…' : '↗'}
            </button>
          </form>
        </div>
      )}

      {showFab ? (
      <button
        type="button"
        onClick={open ? onClose : onOpen}
        className="fixed bottom-5 right-4 z-40 inline-flex items-center gap-2 rounded-full bg-[#06715F] px-4 py-3 text-sm font-semibold text-white shadow-xl shadow-[#06715F]/35 hover:bg-[#0B3D34] focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#06715F] sm:right-6"
        aria-expanded={open}
      >
        {open ? (
          '✕ Close'
        ) : (
          <>
            <LinasStar className="h-4 w-4" color="#FFFFFF" />
            Chat with Linas
          </>
        )}
      </button>
      ) : null}

      {/* Accessible heading for tests / skip targets when widget closed */}
      <h2 className="sr-only">{copy.title}</h2>
    </div>
  );
}
