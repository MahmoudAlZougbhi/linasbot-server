import React, { useState, useEffect } from "react";
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
  CalendarIcon,
  FaceSmileIcon,
  ExclamationTriangleIcon,
  MicrophoneIcon,
  PhotoIcon,
  HandRaisedIcon,
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

  const ChartCard = ({ title, icon: Icon, children }) => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl p-6 shadow-lg border border-slate-100"
    >
      <div className="flex items-center space-x-3 mb-6">
        <div className="p-2 rounded-lg bg-gradient-to-br from-primary-500 to-secondary-500">
          <Icon className="w-5 h-5 text-white" />
        </div>
        <h3 className="text-lg font-bold text-slate-900">{title}</h3>
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
  const escalations = analyticsData?.escalations || {};
  const performance = analyticsData?.performance || {};
  const tokens = analyticsData?.token_usage || {};
  const conversions = analyticsData?.conversions || {};
  const newClients = analyticsData?.new_clients || {};
  const servicesDiscussedToday = analyticsData?.services_discussed_today || {};

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
          icon={CalendarIcon}
          title="Conversations"
          value={overview.total_conversations?.toLocaleString() || "0"}
          subtitle={`${overview.avg_messages_per_conversation || 0} msgs/conv`}
          color="from-green-500 to-emerald-500"
        />
        <StatCard
          icon={CurrencyDollarIcon}
          title="AI Cost"
          value={`${tokens.total_cost_usd?.toFixed(2) || "0.00"}`}
          subtitle={`${(tokens.total_tokens / 1000).toFixed(1) || 0}K tokens ${
            tokens.source === "openai_api" ? "✓ Real" : "≈ Est."
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
            title="Asked But Did Not Book"
            value={conversions.new_clients_asked_not_booked ?? newClients.asked_not_booked_count ?? 0}
            subtitle="New clients who inquired but didn't book"
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
            subtitle={`${newClients.booked_count ?? 0} booked · ${newClients.not_booked_count ?? 0} not booked`}
            color="from-blue-500 to-cyan-500"
          />
        </div>

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
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(newClients.booked_details || []).length === 0 ? (
                <p className="text-sm text-slate-500">No new client bookings in this period.</p>
              ) : (
                (newClients.booked_details || []).map((item, index) => (
                  <div
                    key={index}
                    className="p-3 bg-green-50 rounded-lg border border-green-100"
                  >
                    <p className="text-xs font-mono text-slate-600 mb-1">
                      {item.user_id_masked ?? `...${String(item.user_id || "").slice(-4)}`}
                    </p>
                    <p className="text-xs text-green-700">
                      Services: {(item.services || []).join(", ").replace(/_/g, " ") || "—"}
                    </p>
                  </div>
                ))
              )}
            </div>
          </ChartCard>
          <ChartCard title="Who Asked But Did Not Book (New Clients)" icon={UsersIcon}>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(newClients.asked_not_booked_details || []).length === 0 ? (
                <p className="text-sm text-slate-500">No new clients in this category.</p>
              ) : (
                (newClients.asked_not_booked_details || []).map((item, index) => (
                  <div
                    key={index}
                    className="p-3 bg-amber-50 rounded-lg border border-amber-100"
                  >
                    <p className="text-xs font-mono text-slate-600 mb-1">
                      {item.user_id_masked ?? `...${String(item.user_id || "").slice(-4)}`}
                    </p>
                    <p className="text-xs text-amber-700">
                      Services: {(item.services || []).join(", ").replace(/_/g, " ") || "—"}
                    </p>
                  </div>
                ))
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

        <ChartCard title="Peak Hours Analysis" icon={ClockIcon}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={Object.entries(hourly).map(([hour, count]) => ({
                hour,
                messages: count,
              }))}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="hour" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar
                dataKey="messages"
                fill={COLORS.info}
                radius={[8, 8, 0, 0]}
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
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={[
                  { name: "Positive", value: sentiment.positive || 0 },
                  { name: "Neutral", value: sentiment.neutral || 0 },
                  { name: "Negative", value: sentiment.negative || 0 },
                ]}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                dataKey="value"
              >
                <Cell fill={COLORS.success} />
                <Cell fill={COLORS.warning} />
                <Cell fill={COLORS.danger} />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Services & Appointments */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Most Requested Services" icon={SparklesIcon}>
          <div className="space-y-3">
            {services.most_requested?.slice(0, 5).map((service, index) => (
              <div key={index} className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-slate-700">
                    {service.name}
                  </span>
                  <div className="flex items-center space-x-2">
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
                    style={{ width: `${service.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </ChartCard>

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

      {/* Satisfaction & Escalations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
                  <span className="text-sm font-medium text-orange-800">
                    Human Handover
                  </span>
                </div>
                <span className="text-lg font-bold text-orange-600">
                  {escalations.human_handover || 0}
                </span>
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
