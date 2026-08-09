import { useCallback, useEffect, useRef, useState } from 'react';
import {
  countWords,
  ensureGuestSession,
  getOrCreateGuestSessionId,
  sendGuestMessage,
} from '../../utils/guestChatApi';
import StoreBadges from './StoreBadges';
import LinasStar from './LinasStar';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';

const GATE_FALLBACK = {
  en: 'You’ve reached the guest limit (10 questions). Download the Linas AI app and subscribe to continue.',
  ar: 'وصلت إلى حد الضيف (10 أسئلة). حمّل تطبيق Linas AI واشترك للمتابعة.',
  fr: 'Limite invité atteinte (10 questions). Téléchargez l’app Linas AI et abonnez-vous pour continuer.',
};

const COPY = {
  en: {
    title: 'Talk to Linas',
    subtitle: 'Guest preview — 10 questions, 50 words each.',
    placeholder: 'Message Linas',
    send: 'Send',
    /** @param {number} n */
    remaining: (n) => `${n} of 10 prompts left`,
    /** @param {number} used */
    usedBar: (used) => `${used} of 10 prompts used`,
    wordLimit: 'Each guest question can be at most 50 words.',
    retry: 'Couldn’t start guest chat. Try again.',
    failed: 'Message failed. Please try again.',
    unavailable: 'Linas AI is temporarily unavailable. Please try again in a moment.',
    continueInApp: 'Continue in the app',
    greeting: 'Hi — I’m the public Linas guide. Ask how the product handles DMs, comments, setup, or account access.',
    chips: ['What can Linas answer?', 'How are replies controlled?', 'How does Meta setup work?'],
  },
  ar: {
    title: 'تحدّث مع Linas',
    subtitle: 'معاينة ضيف — 10 أسئلة، 50 كلمة لكل سؤال.',
    placeholder: 'راسل Linas',
    send: 'إرسال',
    /** @param {number} n */
    remaining: (n) => `متبقي ${n} من 10`,
    /** @param {number} used */
    usedBar: (used) => `${used} من 10`,
    wordLimit: 'كل سؤال ضيف بحد أقصى 50 كلمة.',
    retry: 'تعذّر بدء الدردشة. حاول مجدداً.',
    failed: 'فشل الإرسال. حاول مجدداً.',
    unavailable: 'Linas AI غير متاح مؤقتاً. حاول مرة أخرى بعد لحظات.',
    continueInApp: 'تابع في التطبيق',
    greeting: 'مرحباً — أنا دليل Linas العام. اسأل عن الرسائل والتعليقات والإعداد.',
    chips: ['ماذا يجيب Linas؟', 'كيف تُضبط الردود؟', 'كيف يعمل إعداد Meta؟'],
  },
  fr: {
    title: 'Parler à Linas',
    subtitle: 'Aperçu invité — 10 questions, 50 mots max.',
    placeholder: 'Message Linas',
    send: 'Envoyer',
    /** @param {number} n */
    remaining: (n) => `${n} / 10 restantes`,
    /** @param {number} used */
    usedBar: (used) => `${used} / 10 utilisées`,
    wordLimit: 'Chaque question invité fait au plus 50 mots.',
    retry: 'Impossible de démarrer le chat. Réessayez.',
    failed: 'Échec de l’envoi. Réessayez.',
    unavailable: 'Linas AI est temporairement indisponible. Réessayez dans un instant.',
    continueInApp: 'Continuer dans l’app',
    greeting: 'Bonjour — je suis le guide public Linas. Demandez pour les DMs, commentaires ou configuration.',
    chips: ['Que peut répondre Linas ?', 'Comment sont contrôlées les réponses ?', 'Comment marche Meta ?'],
  },
};

/**
 * Guest AI floating widget matching linas-landing-09-guest-ai.jpg.
 * @param {{ open: boolean, onOpen: () => void, onClose: () => void }} props
 */
export default function GuestChatPanel({ open = false, onOpen = () => {}, onClose = () => {} }) {
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
    if (countWords(trimmed) > maxWords) {
      setError(copy.wordLimit);
      return;
    }
    setSending(true);
    setError(null);
    setDraft('');
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'user', content: trimmed }]);
    try {
      const result = await sendGuestMessage(guestId, trimmed, locale);
      setQuestionsRemaining(result.session.questions_remaining);
      setMaxWords(result.session.max_words ?? maxWords);
      if (!result.ok) {
        setGated(true);
        setGateText(
          result.gateMessages?.[locale] || result.gateMessages?.en || GATE_FALLBACK[locale] || GATE_FALLBACK.en,
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
      const status =
        err && typeof err === 'object' && 'status' in err ? Number(/** @type {{status?: number}} */ (err).status) : 0;
      if (message === 'word_limit') {
        setError(copy.wordLimit);
      } else if (status === 503) {
        setError(copy.unavailable);
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

  /** @param {import('react').FormEvent<HTMLFormElement>} event */
  const onSend = async (event) => {
    event.preventDefault();
    await sendContent(draft);
  };

  const used = Math.max(0, 10 - questionsRemaining);

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

          <div className="bg-[#E8F5F1] px-4 py-2 text-xs font-medium text-[#0B3D34]">
            {loading ? '…' : copy.usedBar(used)}
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
            {!loading && !gated && messages.length <= 1 && (
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

      {/* Accessible heading for tests / skip targets when widget closed */}
      <h2 className="sr-only">{copy.title}</h2>
    </div>
  );
}
