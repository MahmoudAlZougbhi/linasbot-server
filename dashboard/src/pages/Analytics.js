import React, { useState, useEffect } from "react";
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
  ArrowUturnLeftIcon,
} from "@heroicons/react/24/outline";
import {
  LineChart,
  Line,
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
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, [timeRange]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      const baseURL =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1"
          ? "http://localhost:8003"
          : window.location.origin;

      const response = await fetch(
        `${baseURL}/api/analytics/summary?time_range=${timeRange}`
      );
      const result = await response.json();

      if (result.success && result.data) {
        setAnalyticsData(result.data);
      } else {
        console.error("Failed to fetch analytics:", result.error);
        setAnalyticsData(null);
      }
    } catch (error) {
      console.error("Error fetching analytics:", error);
      setAnalyticsData(null);
    } finally {
      setLoading(false);
    }
  };

  const COLORS = {
    primary: "#8b5cf6",
    secondary: "#ec4899",
    success: "#10b981",
    warning: "#f59e0b",
    danger: "#ef4444",
    info: "#06b6d4",
  };

  const CHART_COLORS = ["#8b5cf6", "#ec4899", "#06b6d4", "#10b981", "#f59e0b"];

  /** Full token count with commas — avoids "3947.0K" misread as 3947 tokens. */
  const formatTokensFull = (n) => (Number(n) || 0).toLocaleString("en-US");

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

  const overview = analyticsData?.overview || {};
  const daily = analyticsData?.daily_summaries || [];
  const hourly = analyticsData?.hourly_distribution || {};
  const demographics = analyticsData?.demographics || {};
  const sentiment = analyticsData?.sentiment_distribution || {};
  const services = analyticsData?.services || {};
  const appointments = analyticsData?.appointments || {};
  const satisfaction = analyticsData?.satisfaction || {};
  const sessionRatings = analyticsData?.session_ratings || {};
  const escalations = analyticsData?.escalations || {};
  const performance = analyticsData?.performance || {};
  const tokens = analyticsData?.token_usage || {};
  const conversions = analyticsData?.conversions || {};
  const newClients = analyticsData?.new_clients || {};
  const servicesDiscussedToday = analyticsData?.services_discussed_today || {};
  const bookedCount = newClients.booked_count ?? 0;
  const notBookedCount = newClients.not_booked_count ?? 0;
  const askedNotBookedCount =
    conversions.new_clients_asked_not_booked ?? newClients.asked_not_booked_count ?? 0;
  /** New clients with no booking who never got a logged "service_request" event (keyword match). */
  const newClientsNoInquiryCount = Math.max(0, notBookedCount - askedNotBookedCount);

  const timeRangeMeta = analyticsData?.time_range || {};
  const peakHoursPeriodLabel = (() => {
    const s = timeRangeMeta.start_date;
    const e = timeRangeMeta.end_date;
    if (!s || !e) return null;
    try {
      const ds = new Date(s);
      const de = new Date(e);
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
    { name: "Positive", value: sentiment.positive || 0, color: COLORS.success },
    { name: "Neutral", value: sentiment.neutral || 0, color: COLORS.warning },
    { name: "Negative", value: sentiment.negative || 0, color: COLORS.danger },
  ];
  const sentimentTotal = sentimentRows.reduce((sum, r) => sum + r.value, 0);
  const sentimentPieData = sentimentRows.filter((r) => r.value > 0);

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
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          icon={ChatBubbleLeftRightIcon}
          title="Total Messages"
          value={overview.total_messages?.toLocaleString() || "0"}
          subtitle={`${overview.avg_messages_per_day || 0} per day`}
          color="from-blue-500 to-cyan-500"
        />
        <StatCard
          icon={UsersIcon}
          title="Active Users"
          value={overview.total_users?.toLocaleString() || "0"}
          subtitle={`${overview.new_users || 0} new users`}
          color="from-purple-500 to-pink-500"
        />
        <StatCard
          icon={ArrowUturnLeftIcon}
          title="Returning / old clients"
          value={(overview.returning_users ?? 0).toLocaleString()}
          subtitle={`Active in period, first seen before this range · عملاء رجعوا / قدامى ضمن النطاق`}
          color="from-green-500 to-emerald-500"
        />
        <StatCard
          icon={CurrencyDollarIcon}
          title="AI Cost"
          value={`$${tokens.total_cost_usd?.toFixed(2) || "0.00"}`}
          subtitle={`${formatTokensFull(tokens.total_tokens)} tokens · ${
            tokens.source === "openai_api" ? "✓ Real (OpenAI billing)" : "≈ Est. (from message logs)"
          }`}
          color="from-orange-500 to-red-500"
        />
      </div>

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
            value={conversions.new_clients_booked ?? newClients.booked_count ?? 0}
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
            value={servicesDiscussedToday.total_mentions ?? 0}
            subtitle={`${servicesDiscussedToday.unique_clients ?? 0} unique clients`}
            color="from-purple-500 to-pink-500"
          />
          <StatCard
            icon={ChartBarIcon}
            title="Total New Clients"
            value={newClients.total_new_clients ?? 0}
            subtitle={`${bookedCount} booked · ${notBookedCount} not booked`}
            color="from-blue-500 to-cyan-500"
          />
        </div>
        {(newClients.total_new_clients ?? 0) > 0 && (
          <p className="text-sm text-slate-600 max-w-4xl leading-relaxed border border-slate-100 bg-slate-50/80 rounded-xl px-4 py-3">
            <span className="font-semibold text-slate-800">Why “not booked” can be larger than “inquired · no booking”:</span>{" "}
            <span className="text-slate-700">
              “Not booked” counts every new client who did not complete a booking (
              {notBookedCount}). The middle card only counts those where our logs recorded a{" "}
              <em>service keyword / inquiry</em> ({askedNotBookedCount}). The difference (
              {newClientsNoInquiryCount}) are new clients who never triggered that logged inquiry — so they are “not booked” but not in the middle card.
            </span>
            <br />
            <span className="text-slate-600 mt-2 block" dir="rtl">
              <strong>بالعربي:</strong> الرقم {notBookedCount} = كل العملاء الجدد بدون حجز. الرقم {askedNotBookedCount} = منهم فقط اللي انسجل عندهم استفسار خدمة (كلمات مفتاحية). الفرق {newClientsNoInquiryCount} = عملاء جدد ما انسجل عندهم هالاستفسار، لذلك يظهرون ضمن «لم يحجز» فقط وليس في بطاقة الوسط.
            </span>
          </p>
        )}

        {/* Services Discussed Today */}
        {servicesDiscussedToday.by_service?.length > 0 && (
          <ChartCard title="Services Discussed Today" icon={SparklesIcon}>
            <div className="space-y-3">
              {servicesDiscussedToday.by_service.map((item, index) => (
                <div key={index} className="flex justify-between items-center p-2 bg-slate-50 rounded-lg">
                  <span className="text-sm font-medium text-slate-700 capitalize">
                    {item.service?.replace(/_/g, " ")}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-500">{item.mentions} mentions</span>
                    <span className="text-sm font-bold text-primary-600">
                      {item.unique_clients} clients
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
              {(newClients.booked_details || []).length === 0 ? (
                <p className="text-sm text-slate-500">No new client bookings in this period.</p>
              ) : (
                (newClients.booked_details || []).map((item, index) => {
                  const searchQ =
                    item.live_chat_search ||
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
                      {item.phone_display ?? item.user_id ?? "—"}
                    </p>
                    {(item.discussed_services || []).length > 0 && (
                      <p className="text-xs text-slate-600">
                        <span className="font-medium text-slate-700">Discussed: </span>
                        {(item.discussed_services || []).join(", ").replace(/_/g, " ")}
                      </p>
                    )}
                    {(item.booked_services || []).length > 0 && (
                      <p className="text-xs text-green-800 font-medium">
                        Booked: {(item.booked_services || []).join(", ").replace(/_/g, " ")}
                      </p>
                    )}
                    {(!(item.discussed_services || []).length && !(item.booked_services || []).length) && (
                      <p className="text-xs text-green-700">
                        Services: {(item.services || []).join(", ").replace(/_/g, " ") || "—"}
                      </p>
                    )}
                    {(item.services_pricing || []).length > 0 && (
                      <ul className="text-xs text-slate-600 border-t border-green-100/80 pt-2 space-y-1">
                        {(item.services_pricing || []).map((sp, i) => (
                          <li key={i}>
                            <span className="text-slate-700 capitalize">
                              {String(sp.service || "").replace(/_/g, " ")}
                            </span>
                            <span className="text-slate-500"> — </span>
                            <span className="italic">{sp.price_hint}</span>
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
              {(newClients.asked_not_booked_details || []).length === 0 ? (
                <p className="text-sm text-slate-500">No new clients in this category.</p>
              ) : (
                (newClients.asked_not_booked_details || []).map((item, index) => {
                  const searchQ =
                    item.live_chat_search ||
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
                      {item.phone_display ?? item.user_id ?? "—"}
                    </p>
                    <p className="text-xs text-amber-800">
                      <span className="font-medium">Inquired about: </span>
                      {(item.discussed_services || item.services || []).join(", ").replace(/_/g, " ") || "—"}
                    </p>
                    {(item.services_pricing || []).length > 0 && (
                      <ul className="text-xs text-slate-600 border-t border-amber-100/80 pt-2 space-y-1">
                        {(item.services_pricing || []).map((sp, i) => (
                          <li key={i}>
                            <span className="text-slate-700 capitalize">
                              {String(sp.service || "").replace(/_/g, " ")}
                            </span>
                            <span className="text-slate-500"> — </span>
                            <span className="italic">{sp.price_hint}</span>
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
                          <span className="font-medium text-slate-700">Period / الفترة: </span>
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
                data={Object.entries(demographics.languages?.counts || {}).map(
                  ([lang, count]) => ({
                    name: lang.toUpperCase(),
                    value: count,
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
                {Object.keys(demographics.languages?.counts || {}).map(
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
                data={Object.entries(demographics.genders?.counts || {}).map(
                  ([gender, count]) => ({
                    name: gender.charAt(0).toUpperCase() + gender.slice(1),
                    value: count,
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
                    {daily.reduce((sum, d) => sum + d.text_messages, 0)}
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
                    {daily.reduce((sum, d) => sum + d.voice_messages, 0)}
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
                    {daily.reduce((sum, d) => sum + d.image_messages, 0)}
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
            {(services.most_requested || []).length === 0 ? (
              <p className="text-sm text-slate-500">No service requests in this period.</p>
            ) : (
              services.most_requested.slice(0, 5).map((service, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-between items-center gap-2">
                    <span className="text-sm font-medium text-slate-700 lowercase">
                      {service.name}
                    </span>
                    <div className="flex items-center space-x-2 shrink-0">
                      <span className="text-sm text-slate-500">
                        {service.count} requests
                      </span>
                      <span className="text-sm font-bold text-primary-600">
                        {service.percentage}%
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, service.percentage)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </ChartCard>

        <ChartCard title="Most Booked Services" icon={SparklesIcon}>
          <div className="space-y-3">
            {(services.most_booked || []).length === 0 ? (
              <p className="text-sm text-slate-500">No completed bookings in this period.</p>
            ) : (
              services.most_booked.slice(0, 5).map((service, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-between items-center gap-2">
                    <span className="text-sm font-medium text-slate-700 lowercase">
                      {service.name}
                    </span>
                    <div className="flex items-center space-x-2 shrink-0">
                      <span className="text-sm text-slate-500">
                        {service.count} bookings
                      </span>
                      <span className="text-sm font-bold text-primary-600">
                        {service.percentage}%
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, service.percentage)}%` }}
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
                  {appointments.total_booked || 0}
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
                      Unique users transferred to staff · مستخدمين انحوّلوا لموظف
                    </span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-2xl font-bold text-violet-700 block">
                    {escalations.human_handover_unique_users ?? 0}
                  </span>
                  <span className="text-[11px] text-violet-600">
                    {escalations.human_handover || 0} events
                  </span>
                </div>
              </div>
            </div>
            <p className="text-[11px] text-slate-500 leading-snug">
              Percentages below are share of all appointment events in range (
              {appointments.appointment_events_total ?? "—"} total: requested + booked +
              confirmed + rescheduled + cancelled). Not “% of booked only” — avoids {'>'}100%
              when reschedules ≠ bookings.
            </p>
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-green-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-green-600">
                  {appointments.confirmed || 0}
                </p>
                <p className="text-xs text-green-700 mt-1">Confirmed</p>
                <p className="text-xs text-green-600 font-medium">
                  {appointments.confirmation_rate || 0}%
                </p>
              </div>
              <div className="p-3 bg-orange-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-orange-600">
                  {appointments.rescheduled || 0}
                </p>
                <p className="text-xs text-orange-700 mt-1">Rescheduled</p>
                <p className="text-xs text-orange-600 font-medium">
                  {appointments.reschedule_rate || 0}%
                </p>
              </div>
              <div className="p-3 bg-red-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-red-600">
                  {appointments.cancelled || 0}
                </p>
                <p className="text-xs text-red-700 mt-1">Cancelled</p>
                <p className="text-xs text-red-600 font-medium">
                  {appointments.cancellation_rate || 0}%
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
                {satisfaction.satisfaction_rate || 0}%
              </span>
            </div>
            <div className="flex items-center justify-between text-sm text-green-700">
              <span>👍 {satisfaction.likes || 0} Likes</span>
              <span>👎 {satisfaction.dislikes || 0} Dislikes</span>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-700 mb-3">
              Feedback Reasons
            </h4>
            <div className="space-y-2">
              {Object.entries(satisfaction.dislike_reasons || {}).map(
                ([reason, count]) => (
                  <div
                    key={reason}
                    className="flex items-center justify-between p-2 bg-slate-50 rounded"
                  >
                    <span className="text-sm text-slate-600 capitalize">
                      {reason.replace("_", " ")}
                    </span>
                    <span className="text-sm font-medium text-slate-800">
                      {count}
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
                  {sessionRatings.total_ratings || 0} ratings ·{" "}
                  {sessionRatings.unique_raters ?? 0} users
                </span>
              </div>
              <span className="text-3xl font-bold text-amber-700">
                {sessionRatings.average_stars != null
                  ? Number(sessionRatings.average_stars).toFixed(2)
                  : "—"}{" "}
                <span className="text-lg">/ 5</span>
              </span>
            </div>
          </div>
          <div className="space-y-3">
            {[5, 4, 3, 2, 1].map((star) => {
              const byStar = sessionRatings.by_star || {};
              const count = Number(byStar[String(star)] ?? byStar[star] ?? 0);
              const pct = Number(
                sessionRatings.percentages?.[String(star)] ??
                  sessionRatings.percentages?.[star] ??
                  0
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
                  {escalations.total_escalations || 0}
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
                      {escalations.human_handover || 0} events
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-lg font-bold text-orange-600 block">
                    {escalations.human_handover_unique_users ?? 0}
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
                  {escalations.complaints || 0}
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
                  {escalations.technical_issues || 0}
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
                {Math.round(performance.avg_response_time_ms || 0)}ms
              </p>
            </div>
            <div className="p-4 bg-green-50 rounded-xl">
              <p className="text-sm text-green-600 mb-1">Min Response</p>
              <p className="text-2xl font-bold text-green-800">
                {Math.round(performance.min_response_time_ms || 0)}ms
              </p>
            </div>
            <div className="p-4 bg-orange-50 rounded-xl">
              <p className="text-sm text-orange-600 mb-1">P95 Response</p>
              <p className="text-2xl font-bold text-orange-800">
                {Math.round(performance.p95_response_time_ms || 0)}ms
              </p>
            </div>
            <div className="p-4 bg-red-50 rounded-xl">
              <p className="text-sm text-red-600 mb-1">Max Response</p>
              <p className="text-2xl font-bold text-red-800">
                {Math.round(performance.max_response_time_ms || 0)}ms
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
                  {conversions.total_inquiries || 0}
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
                  {conversions.total_appointments || 0}
                </span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-8">
                <div
                  className="bg-gradient-to-r from-green-500 to-emerald-500 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium"
                  style={{ width: `${conversions.conversion_rate || 0}%` }}
                >
                  {conversions.conversion_rate || 0}%
                </div>
              </div>
            </div>
            <div className="mt-4 p-4 bg-green-50 rounded-xl border border-green-200">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-green-800">
                  Conversion Rate
                </span>
                <span className="text-2xl font-bold text-green-600">
                  {conversions.conversion_rate || 0}%
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
