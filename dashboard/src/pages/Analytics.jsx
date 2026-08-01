import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ChartBarIcon,
  UsersIcon,
  ChatBubbleLeftRightIcon,
  CurrencyDollarIcon,
  ClockIcon,
  ArrowTrendingUpIcon,
  GlobeAltIcon,
  SparklesIcon,
  StarIcon,
  CalendarIcon,
  FaceSmileIcon,
  ExclamationTriangleIcon,
  MicrophoneIcon,
  PhotoIcon,
  HandRaisedIcon,
  ArrowPathIcon,
  BellAlertIcon,
} from "@heroicons/react/24/outline";
import { authFetch } from "../utils/authFetch";
import { errorMessage, recordOrEmpty, recordArray, metricNumber, metricRows, metricRecord, metricString, metricStringArray } from "../utils/apiValidate";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";

const Analytics = () => {
  const [timeRange, setTimeRange] = useState(7);
  const [analyticsData, setAnalyticsData] = useState(/** @type {Record<string, unknown> | null} */ (null));
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(/** @type {string | null} */ (null));

  const fetchAnalytics = useCallback(async () => {
    try {
      setLoading(true);
      const baseURL =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1"
          ? "http://localhost:8003"
          : window.location.origin;

      const response = await authFetch(
        `${baseURL}/api/analytics/summary?time_range=${timeRange}`
      );
      const result = await response.json();

      if (!response.ok) {
        setFetchError(`Analytics request failed (${response.status})`);
        setAnalyticsData(null);
        return;
      }
      if (result.success && result.data) {
        setFetchError(null);
        setAnalyticsData(result.data);
      } else {
        setFetchError(result.error || 'Failed to load analytics');
        setAnalyticsData(null);
      }
    } catch (error) {
      setFetchError(errorMessage(error) || 'Failed to load analytics');
      setAnalyticsData(null);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  const COLORS = {
    primary: "#8b5cf6",
    secondary: "#ec4899",
    success: "#10b981",
    warning: "#f59e0b",
    danger: "#ef4444",
    info: "#06b6d4",
  };

  const CHART_COLORS = ["#8b5cf6", "#ec4899", "#06b6d4", "#10b981", "#f59e0b"];

  /** @param {number | string | null | undefined} n */
  const formatTokensFull = (n) => (Number(n) || 0).toLocaleString("en-US");

  /**
   * @param {{ icon: import('react').ComponentType<{ className?: string }>, title: string, value: import('react').ReactNode, subtitle?: string, color: string }} props
   */
  const StatCard = ({ icon: Icon, title, value, subtitle, color }) => (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ scale: 1.02 }}
      className="relative overflow-hidden rounded-2xl bg-white p-6 shadow-lg border border-slate-100"
    >
      <div
        className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${color} opacity-5 rounded-full -mr-16 -mt-16`}
      />
      <div className="relative">
        <div className="flex items-start justify-between mb-4">
          <div
            className={`p-3 rounded-xl bg-gradient-to-br ${color} shadow-lg`}
          >
            <Icon className="w-6 h-6 text-white" />
          </div>
        </div>
        <h3 className="text-sm font-medium text-slate-600 mb-1">{title}</h3>
        {loading ? (
          <div className="h-8 w-24 bg-slate-200 rounded animate-pulse" />
        ) : (
          <p className="text-3xl font-bold text-slate-900 mb-1">{value}</p>
        )}
        {subtitle && (
          <p className="text-xs text-slate-500 font-medium">{subtitle}</p>
        )}
      </div>
    </motion.div>
  );

  /**
   * @param {{ title: string, icon: import('react').ComponentType<{ className?: string }>, children: import('react').ReactNode, subtitle?: string }} props
   */
  const ChartCard = ({ title, icon: Icon, children, subtitle }) => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl p-6 shadow-lg border border-slate-100"
    >
      <div className="flex items-start space-x-3 mb-6">
        <div className="p-2 rounded-lg bg-gradient-to-br from-primary-500 to-secondary-500 shrink-0">
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div className="min-w-0">
          <h3 className="text-lg font-bold text-slate-900">{title}</h3>
          {subtitle ? (
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">{subtitle}</p>
          ) : null}
        </div>
      </div>
      {children}
    </motion.div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-primary-600 mx-auto mb-4"></div>
          <p className="text-slate-600 font-medium">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (fetchError && !analyticsData) {
    return (
      <div className="flex items-center justify-center h-screen px-6">
        <div className="text-center max-w-md">
          <p className="text-lg font-semibold text-slate-900 mb-2">Unable to load analytics</p>
          <p className="text-sm text-slate-600 mb-4">{fetchError}</p>
          <button
            type="button"
            onClick={fetchAnalytics}
            className="px-4 py-2 rounded-xl bg-primary-600 text-white text-sm font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  /** @type {Record<string, unknown>} */
  const overview = recordOrEmpty(analyticsData?.overview);
  /** @type {Record<string, unknown>[]} */
  const daily = recordArray(analyticsData?.daily_summaries);
  /** @type {Record<string, unknown>} */
  const hourly = recordOrEmpty(analyticsData?.hourly_distribution);
  /** @type {Record<string, unknown>} */
  const demographics = recordOrEmpty(analyticsData?.demographics);
  /** @type {Record<string, unknown>} */
  const sentiment = recordOrEmpty(analyticsData?.sentiment_distribution);
  /** @type {Record<string, unknown>} */
  const services = recordOrEmpty(analyticsData?.services);
  /** @type {Record<string, unknown>} */
  const appointments = recordOrEmpty(analyticsData?.appointments);
  /** @type {Record<string, unknown>} */
  const satisfaction = recordOrEmpty(analyticsData?.satisfaction);
  /** @type {Record<string, unknown>} */
  const sessionRatings = recordOrEmpty(analyticsData?.session_ratings);
  /** @type {Record<string, unknown>} */
  const pauseCleared = recordOrEmpty(analyticsData?.pause_cleared_resumes);
  /** @type {Record<string, unknown>} */
  const smartReminders = recordOrEmpty(analyticsData?.smart_reminders);
  /** @type {Record<string, unknown>} */
  const appointmentReschedulesDetail = recordOrEmpty(analyticsData?.appointment_reschedules_detail);
  /** @type {Record<string, unknown>} */
  const escalations = recordOrEmpty(analyticsData?.escalations);
  /** @type {Record<string, unknown>} */
  const performance = recordOrEmpty(analyticsData?.performance);
  /** @type {Record<string, unknown>} */
  const tokens = recordOrEmpty(analyticsData?.token_usage);
  /** @type {Record<string, unknown>} */
  const conversions = recordOrEmpty(analyticsData?.conversions);
  /** @type {Record<string, unknown>} */
  const newClients = recordOrEmpty(analyticsData?.new_clients);
  /** @type {Record<string, unknown>} */
  const servicesDiscussedToday = recordOrEmpty(analyticsData?.services_discussed_today);
  const bookedCount = metricNumber(newClients.booked_count);
  const notBookedCount = metricNumber(newClients.not_booked_count);
  const askedNotBookedCount =
    metricNumber(conversions.new_clients_asked_not_booked) || metricNumber(newClients.asked_not_booked_count);

  /** @type {Record<string, unknown>} */
  const timeRangeMeta = recordOrEmpty(analyticsData?.time_range);
  const peakHoursPeriodLabel = (() => {
    const s = typeof timeRangeMeta.start_date === "string" ? timeRangeMeta.start_date : null;
    const e = typeof timeRangeMeta.end_date === "string" ? timeRangeMeta.end_date : null;
    if (!s || !e) return null;
    try {
      const ds = new Date(s);
      const de = new Date(e);
      /** @type {Intl.DateTimeFormatOptions} */
      const o = { day: "numeric", month: "short", year: "numeric" };
      return `${ds.toLocaleDateString("en-GB", o)} – ${de.toLocaleDateString("en-GB", o)}`;
    } catch {
      return null;
    }
  })();
  /** Full 24h series, chronological (fixes shuffled X axis from object key order). */
  const peakHourlyData = (() => {
    const h = hourly || {};
    const rows = [];
    for (let i = 0; i < 24; i++) {
      const key = `${String(i).padStart(2, "0")}:00`;
      rows.push({ hour: key, messages: Number(h[key] ?? 0) });
    }
    return rows;
  })();

  const sentimentRows = [
    { name: "Positive", value: metricNumber(sentiment.positive), color: COLORS.success },
    { name: "Neutral", value: metricNumber(sentiment.neutral), color: COLORS.warning },
    { name: "Negative", value: metricNumber(sentiment.negative), color: COLORS.danger },
  ];
  const sentimentTotal = sentimentRows.reduce((sum, r) => sum + r.value, 0);
  const sentimentPieData = sentimentRows.filter((r) => r.value > 0);

  /** @param {Record<string, unknown>} row @param {string} field */
  const formatRowWhen = (row, field) => {
    const raw = metricString(row[field]);
    if (!raw) return "—";
    try {
      return new Date(raw).toLocaleString();
    } catch {
      return raw;
    }
  };

  /** @param {unknown} stars */
  const formatRatingStars = (stars) => {
    if (stars == null || metricString(stars) === "") return "—";
    return `${metricString(stars)} / 5`;
  };

  return (
    <div className="space-y-8 pb-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-4xl font-bold gradient-text font-display mb-2">
            Analytics Dashboard
          </h1>
          <p className="text-lg text-slate-600">
            Real-time insights and performance metrics
          </p>
        </div>
        <div className="mt-4 sm:mt-0 flex items-center space-x-3">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="input-field"
          >
            <option value={1}>Last 24 Hours</option>
            <option value={7}>Last 7 Days</option>
            <option value={30}>Last 30 Days</option>
            <option value={90}>Last 90 Days</option>
          </select>
          <button
            onClick={fetchAnalytics}
            className="btn-primary"
            disabled={loading}
          >
            <ArrowTrendingUpIcon className="w-4 h-4 mr-2" />
            Refresh
          </button>
        </div>
      </motion.div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
        <StatCard
          icon={ChatBubbleLeftRightIcon}
          title="Total Messages"
          value={metricNumber(overview.total_messages).toLocaleString()}
          subtitle={`${metricNumber(overview.avg_messages_per_day)} per day`}
          color="from-blue-500 to-cyan-500"
        />
        <StatCard
          icon={UsersIcon}
          title="Active Users"
          value={metricNumber(overview.total_users).toLocaleString()}
          subtitle={`${metricNumber(overview.new_users)} new users`}
          color="from-purple-500 to-pink-500"
        />
        <StatCard
          icon={GlobeAltIcon}
          title="Total clients (all time)"
          value={metricNumber(overview.lifetime_unique_users).toLocaleString()}
          subtitle="Unique users ever recorded in analytics (all-time)"
          color="from-green-500 to-emerald-500"
        />
        <StatCard
          icon={ArrowPathIcon}
          title="Pause → Available"
          value={metricNumber(pauseCleared.unique_users).toLocaleString()}
          subtitle={`${metricNumber(pauseCleared.total)} resume events in selected range (Paused → Available)`}
          color="from-teal-500 to-cyan-500"
        />
        <StatCard
          icon={CurrencyDollarIcon}
          title="AI Cost"
          value={`$${metricNumber(tokens.total_cost_usd).toFixed(2)}`}
          subtitle={`${formatTokensFull(metricNumber(tokens.total_tokens))} tokens · ${
            metricString(tokens.source) === "openai_api" ? "✓ Real (OpenAI billing)" : "≈ Est. (from message logs)"
          }`}
          color="from-orange-500 to-red-500"
        />
      </div>

      {/* Pause → Available: who resumed (detail table) */}
      <ChartCard
        title="Paused → Available — customers"
        subtitle="Recent events in range · Rating = latest star rating logged for that user in range"
        icon={ArrowPathIcon}
      >
        {metricRows(pauseCleared.recent).length === 0 ? (
          <p className="text-sm text-slate-500">
            No pause→available rows in this range.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-600">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Phone</th>
                  <th className="px-3 py-2 font-medium">User</th>
                  <th className="px-3 py-2 font-medium">Appt</th>
                  <th className="px-3 py-2 font-medium">Service</th>
                  <th className="px-3 py-2 font-medium">Rating ★</th>
                  <th className="px-3 py-2 font-medium">Chat</th>
                </tr>
              </thead>
              <tbody>
                {metricRows(pauseCleared.recent).map((row, idx) => {
                  const searchQ = metricString(row.live_chat_search);
                  const chatTo = `/live-chat?search=${encodeURIComponent(searchQ)}`;
                  const whenLabel = formatRowWhen(row, "at");
                  const stars = row.last_session_rating_stars;
                  return (
                    <tr key={idx} className="border-t border-slate-100 hover:bg-slate-50/80">
                      <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{whenLabel}</td>
                      <td className="px-3 py-2 font-mono text-slate-800">{metricString(row.phone_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-600">{metricString(row.user_id_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-800">{row.appointment_id != null ? metricString(row.appointment_id) : "—"}</td>
                      <td className="px-3 py-2 text-slate-700 capitalize">
                        {metricString(row.service).replace(/_/g, " ") || "—"}
                      </td>
                      <td className="px-3 py-2 font-medium text-amber-700">
                        {formatRatingStars(stars)}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={chatTo}
                          className="inline-flex items-center rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white shadow hover:bg-emerald-700"
                        >
                          Chat
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ChartCard>

      {/* Smart reminder — no classified reply */}
      <ChartCard
        title="24h reminder — no classified reply"
        subtitle={`Reminder sent but no classified reply yet (yes / postpone / cancel / talk later) · ${metricNumber(metricRecord(smartReminders.no_reply_to_reminder).count)} sends · ${metricNumber(metricRecord(smartReminders.no_reply_to_reminder).unique_users)} unique users`}
        icon={BellAlertIcon}
      >
        {metricRows(smartReminders.no_response_recent).length === 0 ? (
          <p className="text-sm text-slate-500">
            No reminder sends without a classified reply in this range (or no reminder events logged yet).
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-600">
                  <th className="px-3 py-2 font-medium">Sent</th>
                  <th className="px-3 py-2 font-medium">Appt time</th>
                  <th className="px-3 py-2 font-medium">Phone</th>
                  <th className="px-3 py-2 font-medium">User</th>
                  <th className="px-3 py-2 font-medium">Appt ID</th>
                  <th className="px-3 py-2 font-medium">Rating ★</th>
                  <th className="px-3 py-2 font-medium">Chat</th>
                </tr>
              </thead>
              <tbody>
                {metricRows(smartReminders.no_response_recent).map((row, idx) => {
                  const searchQ = metricString(row.live_chat_search);
                  const chatTo = `/live-chat?search=${encodeURIComponent(searchQ)}`;
                  const sentLabel = formatRowWhen(row, "sent_at");
                  const apptWhen = metricString(row.appointment_at) || "—";
                  const stars = row.last_session_rating_stars;
                  return (
                    <tr key={idx} className="border-t border-slate-100 hover:bg-slate-50/80">
                      <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{sentLabel}</td>
                      <td className="px-3 py-2 text-slate-600">{apptWhen}</td>
                      <td className="px-3 py-2 font-mono text-slate-800">{metricString(row.phone_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-600">{metricString(row.user_id_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-800">{row.appointment_id != null ? metricString(row.appointment_id) : "—"}</td>
                      <td className="px-3 py-2 font-medium text-amber-700">
                        {formatRatingStars(stars)}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={chatTo}
                          className="inline-flex items-center rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white shadow hover:bg-emerald-700"
                        >
                          Chat
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ChartCard>

      {/* Smart reminder — classified replies */}
      <ChartCard
        title="Reminder replies (auto-classified)"
        subtitle={`Total classified replies: ${metricNumber(smartReminders.replies_total)} · ${Object.entries(metricRecord(smartReminders.reply_intents)).map(([k, v]) => `${k}=${v}`).join(" · ") || "—"}`}
        icon={ChatBubbleLeftRightIcon}
      >
        {metricRows(smartReminders.reminder_replies_recent).length === 0 ? (
          <p className="text-sm text-slate-500">
            No classified reminder replies in this range.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-600">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Intent</th>
                  <th className="px-3 py-2 font-medium">Phone</th>
                  <th className="px-3 py-2 font-medium">User</th>
                  <th className="px-3 py-2 font-medium">Appt</th>
                  <th className="px-3 py-2 font-medium">Rating ★</th>
                  <th className="px-3 py-2 font-medium">Chat</th>
                </tr>
              </thead>
              <tbody>
                {metricRows(smartReminders.reminder_replies_recent).map((row, idx) => {
                  const searchQ = metricString(row.live_chat_search);
                  const chatTo = `/live-chat?search=${encodeURIComponent(searchQ)}`;
                  const whenLabel = formatRowWhen(row, "at");
                  /** @type {Record<string, string>} */
                  const intentLabel = {
                    confirm: "Confirm",
                    postpone: "Postpone",
                    cancel: "Cancel",
                    defer: "Talk later",
                    other: "Other",
                  };
                  const intentKey = metricString(row.intent);
                  const stars = row.last_session_rating_stars;
                  return (
                    <tr key={idx} className="border-t border-slate-100 hover:bg-slate-50/80">
                      <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{whenLabel}</td>
                      <td className="px-3 py-2 font-medium text-rose-700">
                        {intentLabel[intentKey] || intentKey || "—"}
                      </td>
                      <td className="px-3 py-2 font-mono text-slate-800">{metricString(row.phone_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-600">{metricString(row.user_id_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-800">{row.appointment_id != null ? metricString(row.appointment_id) : "—"}</td>
                      <td className="px-3 py-2 font-medium text-amber-700">
                        {formatRatingStars(stars)}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={chatTo}
                          className="inline-flex items-center rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white shadow hover:bg-emerald-700"
                        >
                          Chat
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ChartCard>

      {/* CRM reschedule (update_appointment_date) */}
      <ChartCard
        title="CRM reschedule (update appointment)"
        subtitle={`Latest reschedules logged in range · Total events: ${metricNumber(appointmentReschedulesDetail.total)}`}
        icon={CalendarIcon}
      >
        {metricRows(appointmentReschedulesDetail.recent).length === 0 ? (
          <p className="text-sm text-slate-500">
            No CRM reschedule events in this range.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-600">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Phone</th>
                  <th className="px-3 py-2 font-medium">User</th>
                  <th className="px-3 py-2 font-medium">Appt</th>
                  <th className="px-3 py-2 font-medium">Service</th>
                  <th className="px-3 py-2 font-medium">Rating ★</th>
                  <th className="px-3 py-2 font-medium">Chat</th>
                </tr>
              </thead>
              <tbody>
                {metricRows(appointmentReschedulesDetail.recent).map((row, idx) => {
                  const searchQ = metricString(row.live_chat_search);
                  const chatTo = `/live-chat?search=${encodeURIComponent(searchQ)}`;
                  const whenLabel = formatRowWhen(row, "at");
                  const stars = row.last_session_rating_stars;
                  return (
                    <tr key={idx} className="border-t border-slate-100 hover:bg-slate-50/80">
                      <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{whenLabel}</td>
                      <td className="px-3 py-2 font-mono text-slate-800">{metricString(row.phone_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-600">{metricString(row.user_id_masked) || "—"}</td>
                      <td className="px-3 py-2 text-slate-800">{row.appointment_id != null ? metricString(row.appointment_id) : "—"}</td>
                      <td className="px-3 py-2 text-slate-700 capitalize">
                        {metricString(row.service).replace(/_/g, " ") || "—"}
                      </td>
                      <td className="px-3 py-2 font-medium text-amber-700">
                        {formatRatingStars(stars)}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={chatTo}
                          className="inline-flex items-center rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white shadow hover:bg-emerald-700"
                        >
                          Chat
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ChartCard>

      {/* New Client Metrics */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-6"
      >
        <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <UsersIcon className="w-7 h-7 text-primary-500" />
          New Client Metrics
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatCard
            icon={CalendarIcon}
            title="New Clients Booked"
            value={metricNumber(conversions.new_clients_booked) || metricNumber(newClients.booked_count)}
            subtitle="First-time clients who completed booking"
            color="from-green-500 to-emerald-500"
          />
          <StatCard
            icon={UsersIcon}
            title="Inquired (logged) · No booking"
            value={askedNotBookedCount}
            subtitle="Keyword/service inquiry logged in analytics, but no booking"
            color="from-amber-500 to-orange-500"
          />
          <StatCard
            icon={SparklesIcon}
            title="Services Discussed Today"
            value={metricNumber(servicesDiscussedToday.total_mentions)}
            subtitle={`${metricNumber(servicesDiscussedToday.unique_clients)} unique clients`}
            color="from-purple-500 to-pink-500"
          />
          <StatCard
            icon={ChartBarIcon}
            title="Total New Clients"
            value={metricNumber(newClients.total_new_clients)}
            subtitle={`${bookedCount} booked · ${notBookedCount} not booked`}
            color="from-blue-500 to-cyan-500"
          />
        </div>

        {/* Services Discussed Today */}
        {metricRows(servicesDiscussedToday.by_service).length > 0 && (
          <ChartCard title="Services Discussed Today" icon={SparklesIcon}>
            <div className="space-y-3">
              {metricRows(servicesDiscussedToday.by_service).map((item, index) => (
                <div key={index} className="flex justify-between items-center p-2 bg-slate-50 rounded-lg">
                  <span className="text-sm font-medium text-slate-700 capitalize">
                    {metricString(item.service).replace(/_/g, " ")}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-500">{metricNumber(item.mentions)} mentions</span>
                    <span className="text-sm font-bold text-primary-600">
                      {metricNumber(item.unique_clients)} clients
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </ChartCard>
        )}

        {/* Who Booked vs Who Did Not (New Clients Only) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChartCard title="Who Booked (New Clients)" icon={CalendarIcon}>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {metricRows(newClients.booked_details).length === 0 ? (
                <p className="text-sm text-slate-500">No new client bookings in this period.</p>
              ) : (
                metricRows(newClients.booked_details).map((item, index) => {
                  const searchQ =
                    metricString(item.live_chat_search) ||
                    String(item.phone_display || item.user_id || "").replace(/\D/g, "") ||
                    String(item.user_id || "");
                  const chatTo = `/live-chat?search=${encodeURIComponent(searchQ)}`;
                  const rawName =
                    item.customer_name && String(item.customer_name).trim()
                      ? String(item.customer_name).trim()
                      : "";
                  const nameLine = rawName || "Name not on file";
                  return (
                  <div
                    key={index}
                    className="p-3 bg-green-50 rounded-lg border border-green-100 space-y-2"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-800">{nameLine}</p>
                        <p className="text-xs text-slate-500">
                          {rawName ? "Name on file" : "No name in CRM / profile yet"}
                        </p>
                      </div>
                      <Link
                        to={chatTo}
                        className="shrink-0 inline-flex items-center rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white shadow hover:bg-emerald-700"
                      >
                        Open chat
                      </Link>
                    </div>
                    <p className="text-sm font-mono text-slate-700 break-all">
                      {metricString(item.phone_display) || metricString(item.user_id) || "—"}
                    </p>
                    {metricStringArray(item.discussed_services).length > 0 && (
                      <p className="text-xs text-slate-600">
                        <span className="font-medium text-slate-700">Discussed: </span>
                        {metricStringArray(item.discussed_services).join(", ").replace(/_/g, " ")}
                      </p>
                    )}
                    {metricStringArray(item.booked_services).length > 0 && (
                      <p className="text-xs text-green-800 font-medium">
                        Booked: {metricStringArray(item.booked_services).join(", ").replace(/_/g, " ")}
                      </p>
                    )}
                    {!metricStringArray(item.discussed_services).length && !metricStringArray(item.booked_services).length && (
                      <p className="text-xs text-green-700">
                        Services: {metricStringArray(item.services).join(", ").replace(/_/g, " ") || "—"}
                      </p>
                    )}
                    {metricRows(item.services_pricing).length > 0 && (
                      <ul className="text-xs text-slate-600 border-t border-green-100/80 pt-2 space-y-1">
                        {metricRows(item.services_pricing).map((sp, i) => (
                          <li key={i}>
                            <span className="text-slate-700 capitalize">
                              {String(sp.service || "").replace(/_/g, " ")}
                            </span>
                            <span className="text-slate-500"> — </span>
                            <span className="italic">{metricString(sp.price_hint)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  );
                })
              )}
            </div>
          </ChartCard>
          <ChartCard title="Who Asked But Did Not Book (New Clients)" icon={UsersIcon}>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {metricRows(newClients.asked_not_booked_details).length === 0 ? (
                <p className="text-sm text-slate-500">No new clients in this category.</p>
              ) : (
                metricRows(newClients.asked_not_booked_details).map((item, index) => {
                  const searchQ =
                    metricString(item.live_chat_search) ||
                    String(item.phone_display || item.user_id || "").replace(/\D/g, "") ||
                    String(item.user_id || "");
                  const chatTo = `/live-chat?search=${encodeURIComponent(searchQ)}`;
                  const rawName =
                    item.customer_name && String(item.customer_name).trim()
                      ? String(item.customer_name).trim()
                      : "";
                  const nameLine = rawName || "Name not on file";
                  return (
                  <div
                    key={index}
                    className="p-3 bg-amber-50 rounded-lg border border-amber-100 space-y-2"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-800">{nameLine}</p>
                        <p className="text-xs text-slate-500">
                          {rawName ? "Name on file" : "No name in CRM / profile yet"}
                        </p>
                      </div>
                      <Link
                        to={chatTo}
                        className="shrink-0 inline-flex items-center rounded-lg bg-amber-600 px-2.5 py-1.5 text-xs font-medium text-white shadow hover:bg-amber-700"
                      >
                        Open chat
                      </Link>
                    </div>
                    <p className="text-sm font-mono text-slate-700 break-all">
                      {metricString(item.phone_display) || metricString(item.user_id) || "—"}
                    </p>
                    <p className="text-xs text-amber-800">
                      <span className="font-medium">Inquired about: </span>
                      {(metricStringArray(item.discussed_services).length ? metricStringArray(item.discussed_services) : metricStringArray(item.services)).join(", ").replace(/_/g, " ") || "—"}
                    </p>
                    {metricRows(item.services_pricing).length > 0 && (
                      <ul className="text-xs text-slate-600 border-t border-amber-100/80 pt-2 space-y-1">
                        {metricRows(item.services_pricing).map((sp, i) => (
                          <li key={i}>
                            <span className="text-slate-700 capitalize">
                              {metricString(sp.service).replace(/_/g, " ")}
                            </span>
                            <span className="text-slate-500"> — </span>
                            <span className="italic">{metricString(sp.price_hint)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  );
                })
              )}
            </div>
          </ChartCard>
        </div>
      </motion.div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Message Volume Trend" icon={ChartBarIcon}>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={daily}>
              <defs>
                <linearGradient id="colorMessages" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor={COLORS.primary}
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="95%"
                    stopColor={COLORS.primary}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) =>
                  new Date(value).toLocaleDateString("en", {
                    month: "short",
                    day: "numeric",
                  })
                }
              />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="total_messages"
                stroke={COLORS.primary}
                fill="url(#colorMessages)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Peak Hours Analysis"
          icon={ClockIcon}
          subtitle={
            peakHoursPeriodLabel
              ? `Local hour (00:00–23:00) · totals include every day in: ${peakHoursPeriodLabel}`
              : `Local hour (00:00–23:00) · totals include every day in the selected range`
          }
        >
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={peakHourlyData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="hour"
                tick={{ fontSize: 10 }}
                angle={-40}
                textAnchor="end"
                height={56}
                interval={0}
              />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const v = payload[0]?.value;
                  return (
                    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-md text-sm max-w-xs">
                      <p className="font-semibold text-slate-900">{label}</p>
                      {peakHoursPeriodLabel ? (
                        <p className="text-xs text-slate-600 mt-1 leading-snug">
                          <span className="font-medium text-slate-700">Period: </span>
                          {peakHoursPeriodLabel}
                        </p>
                      ) : null}
                      <p className="text-xs text-slate-500 mt-1">
                        Count includes all days in this range (not one calendar day).
                      </p>
                      <p className="text-slate-800 mt-2">
                        messages:{" "}
                        <span className="font-semibold tabular-nums">{v}</span>
                      </p>
                    </div>
                  );
                }}
              />
              <Bar
                dataKey="messages"
                fill={COLORS.info}
                radius={[8, 8, 0, 0]}
                maxBarSize={28}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Demographics */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <ChartCard title="Language Distribution" icon={GlobeAltIcon}>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={Object.entries(metricRecord(metricRecord(demographics.languages).counts)).map(
                  ([lang, count]) => ({
                    name: lang.toUpperCase(),
                    value: metricNumber(count),
                  })
                )}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                dataKey="value"
              >
                {Object.keys(metricRecord(metricRecord(demographics.languages).counts)).map(
                  (entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={CHART_COLORS[index % CHART_COLORS.length]}
                    />
                  )
                )}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Gender Distribution" icon={UsersIcon}>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={Object.entries(metricRecord(metricRecord(demographics.genders).counts)).map(
                  ([gender, count]) => ({
                    name: gender.charAt(0).toUpperCase() + gender.slice(1),
                    value: metricNumber(count),
                  })
                )}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                dataKey="value"
              >
                <Cell fill="#3b82f6" />
                <Cell fill="#ec4899" />
                <Cell fill="#94a3b8" />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Message Types" icon={ChatBubbleLeftRightIcon}>
          <div className="space-y-4">
            {daily.length > 0 && (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <ChatBubbleLeftRightIcon className="w-5 h-5 text-blue-500" />
                    <span className="text-sm font-medium text-slate-700">
                      Text
                    </span>
                  </div>
                  <span className="text-lg font-bold text-slate-900">
                    {daily.reduce((sum, d) => sum + metricNumber(d.text_messages), 0)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <MicrophoneIcon className="w-5 h-5 text-purple-500" />
                    <span className="text-sm font-medium text-slate-700">
                      Voice
                    </span>
                  </div>
                  <span className="text-lg font-bold text-slate-900">
                    {daily.reduce((sum, d) => sum + metricNumber(d.voice_messages), 0)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <PhotoIcon className="w-5 h-5 text-pink-500" />
                    <span className="text-sm font-medium text-slate-700">
                      Image
                    </span>
                  </div>
                  <span className="text-lg font-bold text-slate-900">
                    {daily.reduce((sum, d) => sum + metricNumber(d.image_messages), 0)}
                  </span>
                </div>
              </>
            )}
          </div>
        </ChartCard>

        <ChartCard title="Customer Sentiment" icon={FaceSmileIcon}>
          {sentimentTotal === 0 ? (
            <p className="text-sm text-slate-500 text-center py-10">
              No sentiment labels in this period.
            </p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                  <Pie
                    data={sentimentPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={48}
                    outerRadius={72}
                    paddingAngle={sentimentPieData.length > 1 ? 1 : 0}
                    dataKey="value"
                    nameKey="name"
                    stroke="none"
                    isAnimationActive={true}
                  >
                    {sentimentPieData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value) => [
                      `${Number(value).toLocaleString()} messages`,
                      "Count",
                    ]}
                    labelFormatter={(label) => String(label)}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-4 space-y-2.5 border-t border-slate-100 pt-4">
                {sentimentRows.map((row) => (
                  <div
                    key={row.name}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className="h-3 w-3 shrink-0 rounded-full"
                        style={{ backgroundColor: row.color }}
                        aria-hidden
                      />
                      <span className="truncate font-medium text-slate-800">
                        {row.name}
                      </span>
                    </div>
                    <div className="shrink-0 text-right tabular-nums">
                      <span className="font-semibold text-slate-900">
                        {row.value.toLocaleString()}
                      </span>
                      <span className="ml-2 text-slate-500">
                        (
                        {sentimentTotal > 0
                          ? ((row.value / sentimentTotal) * 100).toFixed(1)
                          : "0.0"}
                        %)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </ChartCard>
      </div>

      {/* Services & Appointments */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Most Requested Services" icon={SparklesIcon}>
          <div className="space-y-3">
            {metricRows(services.most_requested).length === 0 ? (
              <p className="text-sm text-slate-500">No service requests in this period.</p>
            ) : (
              metricRows(services.most_requested).slice(0, 5).map((service, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-between items-center gap-2">
                    <span className="text-sm font-medium text-slate-700 lowercase">
                      {metricString(service.name)}
                    </span>
                    <div className="flex items-center space-x-2 shrink-0">
                      <span className="text-sm text-slate-500">
                        {metricNumber(service.count)} requests
                      </span>
                      <span className="text-sm font-bold text-primary-600">
                        {metricNumber(service.percentage)}%
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, metricNumber(service.percentage))}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </ChartCard>

        <ChartCard title="Most Booked Services" icon={SparklesIcon}>
          <div className="space-y-3">
            {metricRows(services.most_booked).length === 0 ? (
              <p className="text-sm text-slate-500">No completed bookings in this period.</p>
            ) : (
              metricRows(services.most_booked).slice(0, 5).map((service, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-between items-center gap-2">
                    <span className="text-sm font-medium text-slate-700 lowercase">
                      {metricString(service.name)}
                    </span>
                    <div className="flex items-center space-x-2 shrink-0">
                      <span className="text-sm text-slate-500">
                        {metricNumber(service.count)} bookings
                      </span>
                      <span className="text-sm font-bold text-primary-600">
                        {metricNumber(service.percentage)}%
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, metricNumber(service.percentage))}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <ChartCard title="Appointment Status" icon={CalendarIcon}>
          <div className="space-y-4">
            <div className="p-4 bg-blue-50 rounded-xl border border-blue-200">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-blue-800">
                  Total Booked
                </span>
                <span className="text-2xl font-bold text-blue-600">
                  {metricNumber(appointments.total_booked)}
                </span>
              </div>
            </div>
            <div className="p-4 bg-violet-50 rounded-xl border border-violet-200">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <HandRaisedIcon className="w-6 h-6 text-violet-600 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-violet-900 block">
                      Human handover
                    </span>
                    <span className="text-[11px] text-violet-700">
                      Unique users transferred to staff
                    </span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-2xl font-bold text-violet-700 block">
                    {metricNumber(escalations.human_handover_unique_users)}
                  </span>
                  <span className="text-[11px] text-violet-600">
                    {metricNumber(escalations.human_handover)} events
                  </span>
                </div>
              </div>
            </div>
            <p className="text-[11px] text-slate-500 leading-snug">
              Percentages below are share of all appointment events in range (
              {metricNumber(appointments.appointment_events_total) || "—"} total: requested + booked +
              confirmed + rescheduled + cancelled). Not “% of booked only” — avoids {'>'}100%
              when reschedules ≠ bookings.
            </p>
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-green-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-green-600">
                  {metricNumber(appointments.confirmed)}
                </p>
                <p className="text-xs text-green-700 mt-1">Confirmed</p>
                <p className="text-xs text-green-600 font-medium">
                  {metricNumber(appointments.confirmation_rate)}%
                </p>
              </div>
              <div className="p-3 bg-orange-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-orange-600">
                  {metricNumber(appointments.rescheduled)}
                </p>
                <p className="text-xs text-orange-700 mt-1">Rescheduled</p>
                <p className="text-xs text-orange-600 font-medium">
                  {metricNumber(appointments.reschedule_rate)}%
                </p>
              </div>
              <div className="p-3 bg-red-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-red-600">
                  {metricNumber(appointments.cancelled)}
                </p>
                <p className="text-xs text-red-700 mt-1">Cancelled</p>
                <p className="text-xs text-red-600 font-medium">
                  {metricNumber(appointments.cancellation_rate)}%
                </p>
              </div>
            </div>
          </div>
        </ChartCard>
      </div>

      {/* Satisfaction, session ratings & Escalations */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ChartCard title="User Satisfaction" icon={FaceSmileIcon}>
          <div className="mb-6 p-4 bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border border-green-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-green-800">
                Satisfaction Rate
              </span>
              <span className="text-3xl font-bold text-green-600">
                {metricNumber(satisfaction.satisfaction_rate)}%
              </span>
            </div>
            <div className="flex items-center justify-between text-sm text-green-700">
              <span>👍 {metricNumber(satisfaction.likes)} Likes</span>
              <span>👎 {metricNumber(satisfaction.dislikes)} Dislikes</span>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-700 mb-3">
              Feedback Reasons
            </h4>
            <div className="space-y-2">
              {Object.entries(metricRecord(satisfaction.dislike_reasons)).map(
                ([reason, count]) => (
                  <div
                    key={reason}
                    className="flex items-center justify-between p-2 bg-slate-50 rounded"
                  >
                    <span className="text-sm text-slate-600 capitalize">
                      {reason.replace("_", " ")}
                    </span>
                    <span className="text-sm font-medium text-slate-800">
                      {metricNumber(count)}
                    </span>
                  </div>
                )
              )}
            </div>
          </div>
        </ChartCard>

        <ChartCard
          title="Session ratings"
          subtitle="Post-booking feedback (1–5 stars), like Google reviews distribution"
          icon={StarIcon}
        >
          <div className="mb-4 p-4 bg-gradient-to-r from-amber-50 to-yellow-50 rounded-xl border border-amber-200">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="text-sm font-medium text-amber-900 block">
                  Average
                </span>
                <span className="text-xs text-amber-800">
                  {metricNumber(sessionRatings.total_ratings)} ratings ·{" "}
                  {metricNumber(sessionRatings.unique_raters)} users
                </span>
              </div>
              <span className="text-3xl font-bold text-amber-700">
                {sessionRatings.average_stars != null
                  ? metricNumber(sessionRatings.average_stars).toFixed(2)
                  : "—"}{" "}
                <span className="text-lg">/ 5</span>
              </span>
            </div>
          </div>
          <div className="space-y-3">
            {[5, 4, 3, 2, 1].map((star) => {
              const byStar = metricRecord(sessionRatings.by_star);
              const percentages = metricRecord(sessionRatings.percentages);
              const count = metricNumber(byStar[String(star)] ?? byStar[star]);
              const pct = metricNumber(
                percentages[String(star)] ?? percentages[star]
              );
              return (
                <div key={star} className="flex items-center gap-3">
                  <span className="w-8 text-sm font-medium text-slate-700 shrink-0">
                    {star}★
                  </span>
                  <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-400 rounded-full transition-all"
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  <span className="w-14 text-right text-sm text-slate-600 shrink-0">
                    {count}
                  </span>
                </div>
              );
            })}
          </div>
        </ChartCard>

        <ChartCard title="Escalations & Issues" icon={ExclamationTriangleIcon}>
          <div className="space-y-4">
            <div className="p-4 bg-red-50 rounded-xl border border-red-200">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-red-800">
                  Total Escalations
                </span>
                <span className="text-2xl font-bold text-red-600">
                  {metricNumber(escalations.total_escalations)}
                </span>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between p-3 bg-orange-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <HandRaisedIcon className="w-5 h-5 text-orange-600" />
                  <div>
                    <span className="text-sm font-medium text-orange-800 block">
                      Human handover
                    </span>
                    <span className="text-[10px] text-orange-700">
                      {metricNumber(escalations.human_handover)} events
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-lg font-bold text-orange-600 block">
                    {metricNumber(escalations.human_handover_unique_users)}
                  </span>
                  <span className="text-[10px] text-orange-700">unique users</span>
                </div>
              </div>
              <div className="flex items-center justify-between p-3 bg-red-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <ExclamationTriangleIcon className="w-5 h-5 text-red-600" />
                  <span className="text-sm font-medium text-red-800">
                    Complaints
                  </span>
                </div>
                <span className="text-lg font-bold text-red-600">
                  {metricNumber(escalations.complaints)}
                </span>
              </div>
              <div className="flex items-center justify-between p-3 bg-yellow-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <ExclamationTriangleIcon className="w-5 h-5 text-yellow-600" />
                  <span className="text-sm font-medium text-yellow-800">
                    Technical Issues
                  </span>
                </div>
                <span className="text-lg font-bold text-yellow-600">
                  {metricNumber(escalations.technical_issues)}
                </span>
              </div>
            </div>
          </div>
        </ChartCard>
      </div>

      {/* Performance & Conversion */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="System Performance" icon={ClockIcon}>
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-slate-50 rounded-xl">
              <p className="text-sm text-slate-600 mb-1">Avg Response</p>
              <p className="text-2xl font-bold text-slate-900">
                {Math.round(metricNumber(performance.avg_response_time_ms))}ms
              </p>
            </div>
            <div className="p-4 bg-green-50 rounded-xl">
              <p className="text-sm text-green-600 mb-1">Min Response</p>
              <p className="text-2xl font-bold text-green-800">
                {Math.round(metricNumber(performance.min_response_time_ms))}ms
              </p>
            </div>
            <div className="p-4 bg-orange-50 rounded-xl">
              <p className="text-sm text-orange-600 mb-1">P95 Response</p>
              <p className="text-2xl font-bold text-orange-800">
                {Math.round(metricNumber(performance.p95_response_time_ms))}ms
              </p>
            </div>
            <div className="p-4 bg-red-50 rounded-xl">
              <p className="text-sm text-red-600 mb-1">Max Response</p>
              <p className="text-2xl font-bold text-red-800">
                {Math.round(metricNumber(performance.max_response_time_ms))}ms
              </p>
            </div>
          </div>
        </ChartCard>

        <ChartCard title="Conversion Funnel" icon={ChartBarIcon}>
          <div className="space-y-4">
            <div className="relative">
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-slate-700">
                  Total Inquiries
                </span>
                <span className="text-sm font-bold text-slate-800">
                  {metricNumber(conversions.total_inquiries)}
                </span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-8">
                <div className="bg-gradient-to-r from-blue-500 to-cyan-500 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium">
                  100%
                </div>
              </div>
            </div>
            <div className="relative">
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-slate-700">
                  Appointments Booked
                </span>
                <span className="text-sm font-bold text-slate-800">
                  {metricNumber(conversions.total_appointments)}
                </span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-8">
                <div
                  className="bg-gradient-to-r from-green-500 to-emerald-500 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium"
                  style={{ width: `${metricNumber(conversions.conversion_rate)}%` }}
                >
                  {metricNumber(conversions.conversion_rate)}%
                </div>
              </div>
            </div>
            <div className="mt-4 p-4 bg-green-50 rounded-xl border border-green-200">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-green-800">
                  Conversion Rate
                </span>
                <span className="text-2xl font-bold text-green-600">
                  {metricNumber(conversions.conversion_rate)}%
                </span>
              </div>
            </div>
          </div>
        </ChartCard>
      </div>
    </div>
  );
};

export default Analytics;
