import {
  ArrowRightIcon,
  ChartBarIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import {
  NewCustomerBadge,
  SentimentIndicator,
  StatusBadge,
} from "./ConversationIndicators";
import { previewLastMessage } from "./MobileLiveChatView.helpers";

/**
 * @param {{
 *   formatLastRefreshTime: () => string;
 *   handleManualRefresh: () => void;
 *   isRefreshing: boolean;
 *   setMobileFilterSheetOpen: (open: boolean) => void;
 *   liveSearchQuery: string;
 *   setLiveSearchQuery: (value: string) => void;
 *   mobileListSection: string;
 *   setMobileListSection: (section: string) => void;
 *   filteredWaitingQueue: QueueItem[];
 *   filteredWithOperator: LiveChatConversation[];
 *   filteredBotConversations: LiveChatConversation[];
 *   mobileVisibleConversations: Array<QueueItem | LiveChatConversation>;
 *   isLoading: boolean;
 *   buildConversationFromQueueItem: (entry: QueueItem) => LiveChatConversation;
 *   getConversationUnreadCount: (entry: QueueItem | LiveChatConversation) => number;
 *   formatPhoneForDisplay: (phone: string | undefined) => string;
 *   formatConversationListDate: (conv: LiveChatConversation) => string;
 *   openWaitingConversation: (entry: QueueItem) => void;
 *   openConversation: (conv: LiveChatConversation) => void;
 *   mobileFilterSheetOpen: boolean;
 *   botDateFrom: string;
 *   setBotDateFrom: (value: string) => void;
 *   botDateTo: string;
 *   setBotDateTo: (value: string) => void;
 *   hasMoreChats: boolean;
 *   loadingMoreChats: boolean;
 *   loadMoreChats: () => void;
 * }} props
 */
export const MobileLiveChatListPane = ({
  formatLastRefreshTime,
  handleManualRefresh,
  isRefreshing,
  setMobileFilterSheetOpen,
  liveSearchQuery,
  setLiveSearchQuery,
  mobileListSection,
  setMobileListSection,
  filteredWaitingQueue,
  filteredWithOperator,
  filteredBotConversations,
  mobileVisibleConversations,
  isLoading,
  buildConversationFromQueueItem,
  getConversationUnreadCount,
  formatPhoneForDisplay,
  formatConversationListDate,
  openWaitingConversation,
  openConversation,
  mobileFilterSheetOpen,
  botDateFrom,
  setBotDateFrom,
  botDateTo,
  setBotDateTo,
  hasMoreChats,
  loadingMoreChats,
  loadMoreChats,
}) => (
        <>
          <div className="px-4 mobile-safe-top pb-3 border-b border-white/10 bg-slate-950/95 backdrop-blur flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h1 className="text-lg font-semibold">Live Chat</h1>
                <p className="text-xs text-slate-400">{formatLastRefreshTime()}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setMobileFilterSheetOpen(true)}
                  className="p-2 rounded-full bg-white/5 border border-white/10"
                >
                  <ChartBarIcon className="w-5 h-5" />
                </button>
                <button
                  onClick={handleManualRefresh}
                  disabled={isRefreshing}
                  className="p-2 rounded-full bg-emerald-500 text-white disabled:opacity-50"
                >
                  <ArrowRightIcon
                    className={`w-4 h-4 ${isRefreshing ? "animate-spin" : "rotate-[-45deg]"}`}
                  />
                </button>
              </div>
            </div>

            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={liveSearchQuery}
                onChange={(e) => setLiveSearchQuery(e.target.value)}
                placeholder="Search by name or phone..."
                className="w-full rounded-2xl bg-white/5 border border-white/10 pl-10 pr-10 py-3 text-sm text-white placeholder:text-slate-500 outline-none"
              />
              {liveSearchQuery && (
                <button
                  onClick={() => setLiveSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              )}
            </div>

            <div className="grid grid-cols-3 gap-2 mt-3">
              {[
                { key: "queue", label: `Queue (${filteredWaitingQueue.length})` },
                { key: "mine", label: `Mine (${filteredWithOperator.length})` },
                { key: "bot", label: `Bot (${filteredBotConversations.length})` },
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setMobileListSection(tab.key)}
                  className={`rounded-2xl px-3 py-2 text-xs font-medium transition ${
                    mobileListSection === tab.key
                      ? "bg-emerald-500 text-white"
                      : "bg-white/5 text-slate-300 border border-white/10"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {isLoading && mobileVisibleConversations.length === 0 ? (
              <div className="p-4 rounded-3xl bg-white/5 border border-white/10 text-center text-sm text-slate-400">
                Loading conversations...
              </div>
            ) : mobileVisibleConversations.length === 0 ? (
              <div className="p-6 rounded-3xl bg-white/5 border border-white/10 text-center text-sm text-slate-400">
                No conversations in this section.
              </div>
            ) : (
              mobileVisibleConversations.map((/** @type {QueueItem | LiveChatConversation} */ entry) => {
                const isQueueItem = mobileListSection === "queue";
                /** @type {LiveChatConversation} */
                const conv = isQueueItem
                  ? buildConversationFromQueueItem(/** @type {QueueItem} */ (entry))
                  : /** @type {LiveChatConversation} */ (entry);
                const unreadCount = getConversationUnreadCount(isQueueItem ? conv : entry);
                const lastPreview = previewLastMessage(conv.last_message || (isQueueItem ? entry.last_message : null)).trim();
                const queueEntry = /** @type {QueueItem} */ (entry);

                return (
                  <button
                    key={`${conv.user_id}_${conv.conversation_id}`}
                    onClick={() =>
                      isQueueItem ? openWaitingConversation(entry) : openConversation(conv)
                    }
                    className="w-full text-left rounded-3xl p-4 bg-white text-slate-900 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-semibold truncate">{String(conv.user_name || conv.user_id)}</p>
                          <NewCustomerBadge isNew={Boolean(conv.is_new_customer)} />
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <StatusBadge status={String(conv.status || "bot")} />
                          {!isQueueItem && <SentimentIndicator sentiment={String(conv.sentiment || "neutral")} />}
                        </div>
                        <p className="text-xs text-slate-500 mt-2 truncate">
                          {lastPreview ||
                            formatPhoneForDisplay(conv.user_phone || conv.phone_number || "") ||
                            "Open conversation"}
                        </p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-[11px] text-slate-500">
                          {isQueueItem
                            ? `${Math.floor((Number(queueEntry.wait_time_seconds) || 0) / 60)}m`
                            : formatConversationListDate(conv)}
                        </p>
                        {unreadCount > 0 && (
                          <span className="mt-2 inline-flex min-w-[22px] h-[22px] items-center justify-center rounded-full bg-emerald-600 px-1 text-[11px] font-bold text-white">
                            {unreadCount}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })
            )}

            {mobileListSection === "bot" && hasMoreChats && (
              <button
                onClick={loadMoreChats}
                disabled={loadingMoreChats}
                className="w-full rounded-2xl px-4 py-3 bg-white/5 text-slate-200 border border-white/10 disabled:opacity-50"
              >
                {loadingMoreChats ? "Loading..." : "Load more conversations"}
              </button>
            )}
          </div>

          {mobileFilterSheetOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/40"
              onClick={() => setMobileFilterSheetOpen(false)}
            >
              <div
                className="absolute inset-x-0 bottom-0 rounded-t-3xl bg-white p-4 text-slate-900 shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="w-12 h-1.5 rounded-full bg-slate-300 mx-auto mb-4" />
                <h3 className="font-semibold text-base mb-3">Mobile filters</h3>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-slate-500 block mb-1">
                      Bot date from
                    </label>
                    <input
                      type="date"
                      value={botDateFrom}
                      onChange={(e) => setBotDateFrom(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 block mb-1">
                      Bot date to
                    </label>
                    <input
                      type="date"
                      value={botDateTo}
                      onChange={(e) => setBotDateTo(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>
                  <button
                    onClick={() => {
                      setBotDateFrom("");
                      setBotDateTo("");
                      setMobileFilterSheetOpen(false);
                    }}
                    className="w-full btn-ghost"
                  >
                    Clear filters
                  </button>
                </div>
              </div>
            </div>
          )}
        </>

);
