import { useCallback, useEffect, useRef, useState } from 'react';
import {
  countWords,
  ensureGuestSession,
  getOrCreateGuestSessionId,
  sendGuestMessage,
} from '../../utils/guestChatApi';
import { LINAS_BRAND_ASSETS } from '../../constants/linasBrand';
import StoreBadges from './StoreBadges';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';

const GATE_FALLBACK = {
  en: 'You’ve reached the guest limit (10 questions). Download the Linas AI app and subscribe to continue.',
  ar: 'وصلت إلى حد الضيف (10 أسئلة). حمّل تطبيق Linas AI واشترك للمتابعة.',
  fr: 'Limite invité atteinte (10 questions). Téléchargez l’app Linas AI et abonnez-vous pour continuer.',
};

const COPY = {
  en: {
    title: 'Talk to Linas',
    subtitle: 'Guest preview — 10 questions, 50 words each. Sales & product only (no workspace changes).',
    placeholder: 'Ask about Linas AI…',
    send: 'Send',
    /** @param {number} n */
    remaining: (n) => `${n} question${n === 1 ? '' : 's'} left`,
    wordLimit: 'Each guest question can be at most 50 words.',
    retry: 'Couldn’t start guest chat. Try again.',
    failed: 'Message failed. Please try again.',
    continueInApp: 'Continue in the app',
  },
  ar: {
    title: 'تحدّث مع Linas',
    subtitle: 'معاينة ضيف — 10 أسئلة، 50 كلمة لكل سؤال. شرح المنتج فقط (بدون تعديل مساحة العمل).',
    placeholder: 'اسأل عن Linas AI…',
    send: 'إرسال',
    /** @param {number} n */
    remaining: (n) => `متبقي ${n} ${n === 1 ? 'سؤال' : 'أسئلة'}`,
    wordLimit: 'كل سؤال ضيف بحد أقصى 50 كلمة.',
    retry: 'تعذّر بدء الدردشة. حاول مجدداً.',
    failed: 'فشل الإرسال. حاول مجدداً.',
    continueInApp: 'تابع في التطبيق',
  },
  fr: {
    title: 'Parler à Linas',
    subtitle: 'Aperçu invité — 10 questions, 50 mots max. Produit uniquement (pas de modifications).',
    placeholder: 'Posez une question sur Linas AI…',
    send: 'Envoyer',
    /** @param {number} n */
    remaining: (n) => `${n} question${n === 1 ? '' : 's'} restante${n === 1 ? '' : 's'}`,
    wordLimit: 'Chaque question invité fait au plus 50 mots.',
    retry: 'Impossible de démarrer le chat. Réessayez.',
    failed: 'Échec de l’envoi. Réessayez.',
    continueInApp: 'Continuer dans l’app',
  },
};

/**
 * Landing guest chat — wires to /api/guest-ai/* (same limits as mobile guest).
 */
export default function GuestChatPanel() {
  const { locale } = usePublicLandingLocale();
  const copy = COPY[locale] || COPY.en;
  const dir = locale === 'ar' ? 'rtl' : 'ltr';

  const [guestId, setGuestId] = useState(/** @type {string | null} */ (null));
  const [messages, setMessages] = useState(/** @type {Array<{id: string; role: string; content: string}>} */ ([]));
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(/** @type {string | null} */ (null));
  const [questionsRemaining, setQuestionsRemaining] = useState(10);
  const [maxWords, setMaxWords] = useState(50);
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
      setQuestionsRemaining(session.questions_remaining ?? 10);
      setMaxWords(session.max_words ?? 50);
      setGated((session.questions_remaining ?? 0) <= 0);
      if ((session.questions_remaining ?? 0) <= 0) {
        setGateText(GATE_FALLBACK[locale] || GATE_FALLBACK.en);
      }
    } catch {
      setError(copy.retry);
    } finally {
      setLoading(false);
    }
  }, [copy.retry, locale]);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, gated, sending]);

  /** @param {import('react').FormEvent<HTMLFormElement>} event */
  const onSend = async (event) => {
    event.preventDefault();
    if (!guestId || gated || sending) return;
    const content = draft.trim();
    if (!content) return;
    if (countWords(content) > maxWords) {
      setError(copy.wordLimit);
      return;
    }
    setSending(true);
    setError(null);
    setDraft('');
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: 'user', content },
    ]);
    try {
      const result = await sendGuestMessage(guestId, content, locale);
      setQuestionsRemaining(result.session.questions_remaining);
      setMaxWords(result.session.max_words ?? maxWords);
      if (!result.ok) {
        setGated(true);
        setGateText(
          result.gateMessages?.[locale] ||
            result.gateMessages?.en ||
            GATE_FALLBACK[locale] ||
            GATE_FALLBACK.en,
        );
        setMessages(result.session.messages || []);
        return;
      }
      setMessages(result.session.messages || []);
      if ((result.session.questions_remaining ?? 0) <= 0) {
        setGated(true);
        setGateText(GATE_FALLBACK[locale] || GATE_FALLBACK.en);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (message === 'word_limit') {
        setError(copy.wordLimit);
      } else {
        setError(copy.failed);
      }
      try {
        const session = await ensureGuestSession(guestId, locale);
        setMessages(session.messages || []);
        setQuestionsRemaining(session.questions_remaining ?? 10);
        setGated((session.questions_remaining ?? 0) <= 0);
      } catch {
        setMessages((prev) => prev.filter((m) => !String(m.id).startsWith('local-')));
      }
    } finally {
      setSending(false);
    }
  };

  const avatarSrc = sending
    ? LINAS_BRAND_ASSETS.typing
    : gated
      ? LINAS_BRAND_ASSETS.idle
      : LINAS_BRAND_ASSETS.welcome;

  return (
    <section
      id="talk-to-linas"
      className="scroll-mt-24"
      aria-labelledby="guest-chat-heading"
      dir={dir}
    >
      <div className="mx-auto max-w-3xl">
        <div className="mb-6 flex items-end gap-4">
          <img
            src={avatarSrc}
            alt=""
            className="h-16 w-16 rounded-2xl object-cover shadow-lg shadow-[#6D4AFF]/20"
            width={64}
            height={64}
          />
          <div>
            <h2 id="guest-chat-heading" className="font-display text-3xl font-bold text-[#2A1B4A]">
              {copy.title}
            </h2>
            <p className="mt-1 text-sm text-[#6B5B85]">{copy.subtitle}</p>
          </div>
        </div>

        <div className="overflow-hidden rounded-3xl border border-[#E4DCF2] bg-white/90 shadow-[0_20px_60px_rgba(109,74,255,0.12)] backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-[#EFE8F8] bg-[#EDE5FF]/50 px-4 py-3">
            <p className="text-sm font-semibold text-[#4C2BB8]">
              {loading ? '…' : copy.remaining(questionsRemaining)}
            </p>
            <p className="text-xs text-[#9B8BB5]">≤{maxWords} words</p>
          </div>

          <div
            ref={listRef}
            className="flex max-h-[min(28rem,55vh)] min-h-[16rem] flex-col gap-3 overflow-y-auto px-4 py-4"
            role="log"
            aria-live="polite"
          >
            {loading && (
              <p className="text-sm text-[#6B5B85]">Connecting to Linas…</p>
            )}
            {!loading &&
              messages.map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.id}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <img
                        src={LINAS_BRAND_ASSETS.avatarChat}
                        alt=""
                        className="mr-2 mt-1 h-8 w-8 rounded-full object-cover"
                        width={32}
                        height={32}
                      />
                    )}
                    <div
                      className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                        isUser
                          ? 'bg-[#6D4AFF] text-white'
                          : 'bg-[#EDE5FF] text-[#2A1B4A]'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                );
              })}
            {gated && gateText && (
              <div className="rounded-2xl border border-[#D4C6F0] bg-[#F3EEFA] p-4 text-sm text-[#2A1B4A]">
                <p className="font-semibold">{gateText}</p>
                <p className="mt-3 text-xs font-medium uppercase tracking-wide text-[#6B5B85]">
                  {copy.continueInApp}
                </p>
                <div className="mt-3">
                  <StoreBadges compact />
                </div>
              </div>
            )}
          </div>

          {error && (
            <p className="border-t border-[#EFE8F8] px-4 py-2 text-sm text-[#DC2626]" role="alert">
              {error}
            </p>
          )}

          <form
            onSubmit={onSend}
            className="flex gap-2 border-t border-[#EFE8F8] bg-[#F7F4FC]/80 p-3"
          >
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
              className="min-w-0 flex-1 rounded-xl border border-[#E4DCF2] bg-white px-3 py-2.5 text-sm text-[#2A1B4A] placeholder:text-[#9B8BB5] focus:border-[#6D4AFF] focus:outline-none focus:ring-2 focus:ring-[#6D4AFF]/30 disabled:opacity-60"
              maxLength={2000}
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={loading || gated || sending || !draft.trim()}
              className="rounded-xl bg-[#6D4AFF] px-4 py-2.5 text-sm font-semibold text-white shadow-md disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sending ? '…' : copy.send}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
