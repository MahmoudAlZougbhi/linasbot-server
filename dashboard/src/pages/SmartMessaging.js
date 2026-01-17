import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MagnifyingGlassIcon,
  CalendarIcon,
  ClockIcon,
  EnvelopeIcon,
  PaperAirplaneIcon,
  CheckCircleIcon,
  ChartBarIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
  EyeIcon,
  XMarkIcon,
  CheckIcon,
  UserIcon,
  Squares2X2Icon,
  InboxIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";

const SmartMessaging = () => {
  const [activeTab, setActiveTab] = useState("sent");
  const [sentMessages, setSentMessages] = useState([]);
  const [messageTemplates, setMessageTemplates] = useState({});
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [editedTemplates, setEditedTemplates] = useState({});
  const [savingTemplate, setSavingTemplate] = useState(null);
  const [selectedLanguage, setSelectedLanguage] = useState("ar");
  const [testPhoneNumber, setTestPhoneNumber] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [sendingTest, setSendingTest] = useState(false);
  const [templateStates, setTemplateStates] = useState({});

  // NEW: Filter and pagination state
  const [selectedMessageType, setSelectedMessageType] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const RECORDS_PER_PAGE = 20;

  // NEW: Smart Messages control states
  const [smartMessagingEnabled, setSmartMessagingEnabled] = useState(true);
  const [previewBeforeSend, setPreviewBeforeSend] = useState(true);
  const [pendingMessages, setPendingMessages] = useState([]);
  const [selectedPendingMessages, setSelectedPendingMessages] = useState([]);
  const [serviceMappings, setServiceMappings] = useState({});
  const [availableServices, setAvailableServices] = useState([]);
  const [availableTemplates, setAvailableTemplates] = useState([]);

  // Fetch real data from API
  useEffect(() => {
    fetchSmartMessagingData();
    fetchSmartMessagingSettings();
    fetchPendingMessages();
    fetchServiceMappings();
  }, []);

  // Fetch smart messaging settings (global toggle, preview mode)
  const fetchSmartMessagingSettings = async () => {
    try {
      const response = await fetch("/api/smart-messaging/settings");
      const result = await response.json();
      if (result.success) {
        setSmartMessagingEnabled(result.settings?.enabled ?? true);
        setPreviewBeforeSend(result.settings?.previewBeforeSend ?? true);
      }
    } catch (error) {
      console.error("Error fetching smart messaging settings:", error);
    }
  };

  // Fetch pending approval messages
  const fetchPendingMessages = async () => {
    try {
      const response = await fetch("/api/smart-messaging/preview-queue?status=pending_approval");
      const result = await response.json();
      if (result.success) {
        setPendingMessages(result.messages || []);
      }
    } catch (error) {
      console.error("Error fetching pending messages:", error);
    }
  };

  // Fetch service-template mappings
  const fetchServiceMappings = async () => {
    try {
      const [mappingsResponse, servicesResponse] = await Promise.all([
        fetch("/api/smart-messaging/service-mappings"),
        fetch("/api/smart-messaging/services")
      ]);

      const mappingsResult = await mappingsResponse.json();
      const servicesResult = await servicesResponse.json();

      if (mappingsResult.success) {
        setServiceMappings(mappingsResult.mappings || {});
      }
      if (servicesResult.success) {
        setAvailableServices(servicesResult.services || []);
        setAvailableTemplates(servicesResult.templates || []);
      }
    } catch (error) {
      console.error("Error fetching service mappings:", error);
    }
  };

  // Toggle smart messaging on/off
  const handleToggleSmartMessaging = async () => {
    try {
      const response = await fetch("/api/smart-messaging/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !smartMessagingEnabled })
      });
      const result = await response.json();
      if (result.success) {
        setSmartMessagingEnabled(!smartMessagingEnabled);
        toast.success(smartMessagingEnabled ? "Smart Messaging disabled" : "Smart Messaging enabled");
      } else {
        toast.error("Failed to toggle smart messaging");
      }
    } catch (error) {
      console.error("Error toggling smart messaging:", error);
      toast.error("Failed to toggle smart messaging");
    }
  };

  // Toggle preview before send setting
  const handleTogglePreviewBeforeSend = async () => {
    try {
      const response = await fetch("/api/smart-messaging/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ previewBeforeSend: !previewBeforeSend })
      });
      const result = await response.json();
      if (result.success) {
        setPreviewBeforeSend(!previewBeforeSend);
        toast.success(previewBeforeSend ? "Preview mode disabled" : "Preview mode enabled");
      } else {
        toast.error("Failed to update setting");
      }
    } catch (error) {
      console.error("Error updating preview setting:", error);
      toast.error("Failed to update setting");
    }
  };

  // Approve a pending message
  const handleApproveMessage = async (messageId) => {
    try {
      const response = await fetch(`/api/smart-messaging/preview-queue/${messageId}/approve`, {
        method: "POST"
      });
      const result = await response.json();
      if (result.success) {
        toast.success("Message approved!");
        fetchPendingMessages();
      } else {
        toast.error("Failed to approve message");
      }
    } catch (error) {
      console.error("Error approving message:", error);
      toast.error("Failed to approve message");
    }
  };

  // Reject a pending message
  const handleRejectMessage = async (messageId) => {
    try {
      const response = await fetch(`/api/smart-messaging/preview-queue/${messageId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Manually rejected" })
      });
      const result = await response.json();
      if (result.success) {
        toast.success("Message rejected");
        fetchPendingMessages();
      } else {
        toast.error("Failed to reject message");
      }
    } catch (error) {
      console.error("Error rejecting message:", error);
      toast.error("Failed to reject message");
    }
  };

  // Batch approve selected messages
  const handleBatchApprove = async () => {
    if (selectedPendingMessages.length === 0) return;
    try {
      const response = await fetch("/api/smart-messaging/preview-queue/batch-approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_ids: selectedPendingMessages })
      });
      const result = await response.json();
      if (result.success) {
        toast.success(`Approved ${result.total_approved} messages`);
        setSelectedPendingMessages([]);
        fetchPendingMessages();
      } else {
        toast.error("Failed to batch approve");
      }
    } catch (error) {
      console.error("Error batch approving:", error);
      toast.error("Failed to batch approve");
    }
  };

  // Batch reject selected messages
  const handleBatchReject = async () => {
    if (selectedPendingMessages.length === 0) return;
    try {
      const response = await fetch("/api/smart-messaging/preview-queue/batch-reject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_ids: selectedPendingMessages, reason: "Batch rejected" })
      });
      const result = await response.json();
      if (result.success) {
        toast.success(`Rejected ${result.total_rejected} messages`);
        setSelectedPendingMessages([]);
        fetchPendingMessages();
      } else {
        toast.error("Failed to batch reject");
      }
    } catch (error) {
      console.error("Error batch rejecting:", error);
      toast.error("Failed to batch reject");
    }
  };

  // Toggle template for a service
  const handleToggleServiceTemplate = async (serviceId, templateId) => {
    const currentValue = serviceMappings[serviceId]?.templates?.[templateId] ?? true;
    const newMappings = { ...serviceMappings };

    if (!newMappings[serviceId]) {
      newMappings[serviceId] = { templates: {} };
    }
    if (!newMappings[serviceId].templates) {
      newMappings[serviceId].templates = {};
    }
    newMappings[serviceId].templates[templateId] = !currentValue;
    setServiceMappings(newMappings);
  };

  // Save service mappings
  const handleSaveServiceMappings = async () => {
    try {
      for (const serviceId of Object.keys(serviceMappings)) {
        await fetch(`/api/smart-messaging/service-mappings/${serviceId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            templates: serviceMappings[serviceId]?.templates || {}
          })
        });
      }
      toast.success("Service mappings saved!");
    } catch (error) {
      console.error("Error saving service mappings:", error);
      toast.error("Failed to save service mappings");
    }
  };

  // Toggle select all pending messages
  const handleSelectAllPending = () => {
    if (selectedPendingMessages.length === pendingMessages.length) {
      setSelectedPendingMessages([]);
    } else {
      setSelectedPendingMessages(pendingMessages.map(m => m.message_id));
    }
  };

  // Toggle select single pending message
  const handleToggleSelectPending = (messageId) => {
    if (selectedPendingMessages.includes(messageId)) {
      setSelectedPendingMessages(selectedPendingMessages.filter(id => id !== messageId));
    } else {
      setSelectedPendingMessages([...selectedPendingMessages, messageId]);
    }
  };

  const fetchSmartMessagingData = async () => {
    try {
      setLoading(true);

      // Fetch scheduler status
      const statusResponse = await fetch("/api/smart-messaging/status");
      const statusResult = await statusResponse.json();

      if (statusResult.success) {
        setSchedulerStatus(statusResult);
      }

      // ✅ NEW: Fetch detailed messages (both sent and scheduled)
      const messagesResponse = await fetch(
        "/api/smart-messaging/messages?status=all"
      );
      const messagesResult = await messagesResponse.json();

      if (messagesResult.success) {
        // Display all messages (sent + scheduled combined)
        setSentMessages(messagesResult.messages || []);
      } else {
        console.warn("Failed to fetch messages detail:", messagesResult.error);
        setSentMessages([]);
      }

      // Fetch templates
      const templatesResponse = await fetch("/api/smart-messaging/templates");
      const templatesResult = await templatesResponse.json();

      if (templatesResult.success) {
        setMessageTemplates(templatesResult.templates);
        // Initialize edited templates with current values
        setEditedTemplates(
          JSON.parse(JSON.stringify(templatesResult.templates))
        );
        // selectedLanguage is now a single string, not per-template
        // Already initialized to "ar" in useState
      }
    } catch (error) {
      console.error("Error fetching smart messaging data:", error);
      toast.error("Failed to load smart messaging data");
    } finally {
      setLoading(false);
    }
  };

  const handleTemplateChange = (templateId, language, value) => {
    setEditedTemplates((prev) => ({
      ...prev,
      [templateId]: {
        ...prev[templateId],
        [language]: value,
      },
    }));
  };

  const handleSaveTemplate = async (templateId) => {
    try {
      setSavingTemplate(templateId);

      const response = await fetch(
        `/api/smart-messaging/templates/${templateId}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ar: editedTemplates[templateId].ar,
            en: editedTemplates[templateId].en,
            fr: editedTemplates[templateId].fr,
          }),
        }
      );

      const result = await response.json();

      if (result.success) {
        toast.success("Template saved successfully!");
        // Update the original templates
        setMessageTemplates((prev) => ({
          ...prev,
          [templateId]: { ...editedTemplates[templateId] },
        }));
      } else {
        toast.error(`Failed to save template: ${result.error}`);
      }
    } catch (error) {
      console.error("Error saving template:", error);
      toast.error("Failed to save template");
    } finally {
      setSavingTemplate(null);
    }
  };

  // Filter messages based on search query AND message type
  const allFilteredMessages = sentMessages
    .filter((message) => {
      // Filter by type
      if (
        selectedMessageType !== "all" &&
        message.message_type !== selectedMessageType
      ) {
        return false;
      }

      // Filter by search query
      if (!searchQuery) return true;

      const searchLower = searchQuery.toLowerCase();
      return (
        message.customer_name?.toLowerCase().includes(searchLower) ||
        message.customer_phone?.toLowerCase().includes(searchLower) ||
        message.message_type?.toLowerCase().includes(searchLower) ||
        message.status?.toLowerCase().includes(searchLower)
      );
    })
    .sort((a, b) => {
      // Sort in ascending order by full datetime (date AND time)
      // Use send_at for scheduled messages, sent_at for sent messages
      const timeA = new Date(
        a.send_at || a.sent_at || a.created_at || a.scheduled_at || 0
      ).getTime();
      const timeB = new Date(
        b.send_at || b.sent_at || b.created_at || b.scheduled_at || 0
      ).getTime();
      return timeA - timeB;
    });

  // Pagination
  const totalPages = Math.ceil(allFilteredMessages.length / RECORDS_PER_PAGE);
  const startIndex = (currentPage - 1) * RECORDS_PER_PAGE;
  const endIndex = startIndex + RECORDS_PER_PAGE;
  const filteredMessages = allFilteredMessages.slice(startIndex, endIndex);

  // Smart pagination: Generate page numbers based on current page
  const getPageNumbers = () => {
    const pages = [];
    const N = totalPages;
    const n = currentPage;

    // Case 1: Current page < 5
    if (n < 5) {
      // Show pages 1-5 (or less if N < 5)
      for (let i = 1; i <= Math.min(5, N); i++) {
        pages.push(i);
      }
      // Add ellipsis and last page if N > 5
      if (N > 5) {
        pages.push("...");
        pages.push(N);
      }
    }
    // Case 2: Current page > N - 4
    else if (n > N - 4) {
      // Show first page
      pages.push(1);
      // Add ellipsis if there's a gap
      if (N > 5) {
        pages.push("...");
      }
      // Show last 5 pages (or fewer if N is small)
      for (let i = Math.max(1, N - 4); i <= N; i++) {
        if (!pages.includes(i)) {
          pages.push(i);
        }
      }
    }
    // Case 3: Middle case
    else {
      // Show first page
      pages.push(1);
      pages.push("...");
      // Show n-1, n, n+1
      pages.push(n - 1);
      pages.push(n);
      pages.push(n + 1);
      pages.push("...");
      // Show last page
      pages.push(N);
    }

    return pages;
  };

  const pageNumbers = getPageNumbers();

  // Count messages by type
  const messageTypesCounts = {
    all: sentMessages.length,
    reminder_24h: sentMessages.filter((m) => m.message_type === "reminder_24h")
      .length,
    same_day_checkin: sentMessages.filter(
      (m) => m.message_type === "same_day_checkin"
    ).length,
    post_session_feedback: sentMessages.filter(
      (m) => m.message_type === "post_session_feedback"
    ).length,
    one_month_followup: sentMessages.filter(
      (m) => m.message_type === "one_month_followup"
    ).length,
    no_show_followup: sentMessages.filter(
      (m) => m.message_type === "no_show_followup"
    ).length,
    missed_yesterday: sentMessages.filter(
      (m) => m.message_type === "missed_yesterday"
    ).length,
    missed_this_month: sentMessages.filter(
      (m) => m.message_type === "missed_this_month"
    ).length,
    attended_yesterday: sentMessages.filter(
      (m) => m.message_type === "attended_yesterday"
    ).length,
  };

  const getMessageTypeInfo = (type) => {
    const types = {
      reminder_24h: {
        name: "24h Reminder",
        color: "bg-blue-100 text-blue-700",
        icon: ClockIcon,
      },
      same_day_checkin: {
        name: "Same Day",
        color: "bg-purple-100 text-purple-700",
        icon: CalendarIcon,
      },
      post_session_feedback: {
        name: "Feedback",
        color: "bg-green-100 text-green-700",
        icon: CheckCircleIcon,
      },
      no_show_followup: {
        name: "No-Show",
        color: "bg-red-100 text-red-700",
        icon: ExclamationTriangleIcon,
      },
      one_month_followup: {
        name: "1-Month",
        color: "bg-indigo-100 text-indigo-700",
        icon: SparklesIcon,
      },
      missed_yesterday: {
        name: "Missed Yesterday",
        color: "bg-orange-100 text-orange-700",
        icon: ExclamationTriangleIcon,
      },
      missed_this_month: {
        name: "Missed Month",
        color: "bg-red-100 text-red-700",
        icon: ExclamationTriangleIcon,
      },
      attended_yesterday: {
        name: "Thank You",
        color: "bg-green-100 text-green-700",
        icon: CheckCircleIcon,
      },
    };
    return types[type] || types.reminder_24h;
  };

  const getTemplateIcon = (templateId) => {
    const icons = {
      reminder_24h: ClockIcon,
      same_day_checkin: CalendarIcon,
      post_session_feedback: CheckCircleIcon,
      no_show_followup: ExclamationTriangleIcon,
      one_month_followup: SparklesIcon,
      missed_yesterday: ExclamationTriangleIcon,
      missed_this_month: ExclamationTriangleIcon,
      attended_yesterday: CheckCircleIcon,
    };
    return icons[templateId] || ClockIcon;
  };

  const getTemplateColor = (templateId) => {
    const colors = {
      reminder_24h: "from-blue-500 to-cyan-500",
      same_day_checkin: "from-purple-500 to-pink-500",
      post_session_feedback: "from-green-500 to-emerald-500",
      no_show_followup: "from-orange-500 to-red-500",
      one_month_followup: "from-indigo-500 to-purple-500",
      missed_yesterday: "from-orange-400 to-orange-600",
      missed_this_month: "from-red-400 to-red-600",
      attended_yesterday: "from-green-400 to-green-600",
    };
    return colors[templateId] || "from-blue-500 to-cyan-500";
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  const stats = schedulerStatus?.statistics || {};

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-4xl font-bold gradient-text font-display mb-2">
            Smart Messaging
          </h1>
          <p className="text-xl text-slate-600">
            Automated messages and appointment reminders
          </p>
        </div>

        <div className="mt-4 sm:mt-0 flex items-center space-x-3">
          {/* Smart Messaging Toggle */}
          <div className={`flex items-center space-x-2 px-4 py-2 rounded-lg border ${
            smartMessagingEnabled
              ? 'bg-green-50 border-green-200'
              : 'bg-slate-50 border-slate-200'
          }`}>
            <span className={`text-sm font-medium ${
              smartMessagingEnabled ? 'text-green-700' : 'text-slate-500'
            }`}>
              {smartMessagingEnabled ? 'Enabled' : 'Disabled'}
            </span>
            <button
              onClick={handleToggleSmartMessaging}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                smartMessagingEnabled
                  ? "bg-green-500 focus:ring-green-500"
                  : "bg-slate-300 focus:ring-slate-400"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm ${
                  smartMessagingEnabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          {/* Scheduler Status */}
          {schedulerStatus?.scheduler_running && (
            <div className="flex items-center space-x-2 px-4 py-2 bg-green-50 border border-green-200 rounded-lg">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="text-sm font-medium text-green-700">
                Scheduler Running
              </span>
            </div>
          )}
        </div>
      </motion.div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="card"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600 mb-1">Sent Today</p>
              <p className="text-2xl font-bold text-slate-800">
                {stats.sent_today || 0}
              </p>
            </div>
            <div className="p-3 bg-green-100 rounded-lg">
              <PaperAirplaneIcon className="w-6 h-6 text-green-600" />
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="card"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600 mb-1">Sent This Week</p>
              <p className="text-2xl font-bold text-slate-800">
                {stats.sent_this_week || 0}
              </p>
            </div>
            <div className="p-3 bg-blue-100 rounded-lg">
              <ClockIcon className="w-6 h-6 text-blue-600" />
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600 mb-1">Sent This Month</p>
              <p className="text-2xl font-bold text-slate-800">
                {stats.sent_this_month || 0}
              </p>
            </div>
            <div className="p-3 bg-purple-100 rounded-lg">
              <ChartBarIcon className="w-6 h-6 text-purple-600" />
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="card"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600 mb-1">Active Templates</p>
              <p className="text-2xl font-bold text-slate-800">
                {Object.keys(messageTemplates).length}
              </p>
            </div>
            <div className="p-3 bg-orange-100 rounded-lg">
              <EnvelopeIcon className="w-6 h-6 text-orange-600" />
            </div>
          </div>
        </motion.div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-slate-100 p-1 rounded-lg">
        <button
          onClick={() => setActiveTab("sent")}
          className={`flex-1 py-2 px-4 rounded-md font-medium transition-all ${
            activeTab === "sent"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Sent Messages
        </button>
        <button
          onClick={() => setActiveTab("templates")}
          className={`flex-1 py-2 px-4 rounded-md font-medium transition-all ${
            activeTab === "templates"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Message Templates
        </button>
        <button
          onClick={() => setActiveTab("mappings")}
          className={`flex-1 py-2 px-4 rounded-md font-medium transition-all ${
            activeTab === "mappings"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Service Mappings
        </button>
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        {activeTab === "sent" && (
          <motion.div
            key="sent"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="card"
          >
            {/* Search Bar */}
            <div className="mb-4">
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by customer name, phone, or message type..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
            </div>

            {/* Message Type Filter (Colored Buttons) */}
            <div className="mb-4">
              <p className="text-xs font-semibold text-slate-700 mb-3">
                FILTER BY MESSAGE TYPE:
              </p>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                {/* All Button */}
                <button
                  onClick={() => {
                    setSelectedMessageType("all");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "all"
                      ? "ring-2 ring-offset-2 ring-primary-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "all"
                      ? "bg-gradient-to-br from-slate-500 to-slate-600 text-white"
                      : "bg-slate-100 text-slate-700 border border-slate-300"
                  }`}
                >
                  <div className="font-bold text-sm">All</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.all}
                  </div>
                </button>

                {/* 24h Reminder */}
                <button
                  onClick={() => {
                    setSelectedMessageType("reminder_24h");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "reminder_24h"
                      ? "ring-2 ring-offset-2 ring-blue-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "reminder_24h"
                      ? "bg-gradient-to-br from-blue-500 to-blue-600 text-white"
                      : "bg-blue-100 text-blue-700 border border-blue-300"
                  }`}
                >
                  <div className="font-bold text-sm">24h Reminder</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.reminder_24h}
                  </div>
                </button>

                {/* Same Day Check-in */}
                <button
                  onClick={() => {
                    setSelectedMessageType("same_day_checkin");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "same_day_checkin"
                      ? "ring-2 ring-offset-2 ring-purple-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "same_day_checkin"
                      ? "bg-gradient-to-br from-purple-500 to-purple-600 text-white"
                      : "bg-purple-100 text-purple-700 border border-purple-300"
                  }`}
                >
                  <div className="font-bold text-sm">Same Day</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.same_day_checkin}
                  </div>
                </button>

                {/* Post Session Feedback */}
                <button
                  onClick={() => {
                    setSelectedMessageType("post_session_feedback");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "post_session_feedback"
                      ? "ring-2 ring-offset-2 ring-green-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "post_session_feedback"
                      ? "bg-gradient-to-br from-green-500 to-green-600 text-white"
                      : "bg-green-100 text-green-700 border border-green-300"
                  }`}
                >
                  <div className="font-bold text-sm">Feedback</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.post_session_feedback}
                  </div>
                </button>

                {/* 1-Month Follow-up */}
                <button
                  onClick={() => {
                    setSelectedMessageType("one_month_followup");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "one_month_followup"
                      ? "ring-2 ring-offset-2 ring-indigo-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "one_month_followup"
                      ? "bg-gradient-to-br from-indigo-500 to-indigo-600 text-white"
                      : "bg-indigo-100 text-indigo-700 border border-indigo-300"
                  }`}
                >
                  <div className="font-bold text-sm">1-Month</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.one_month_followup}
                  </div>
                </button>

                {/* No-Show Follow-up */}
                <button
                  onClick={() => {
                    setSelectedMessageType("no_show_followup");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "no_show_followup"
                      ? "ring-2 ring-offset-2 ring-red-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "no_show_followup"
                      ? "bg-gradient-to-br from-red-500 to-red-600 text-white"
                      : "bg-red-100 text-red-700 border border-red-300"
                  }`}
                >
                  <div className="font-bold text-sm">No-Show</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.no_show_followup}
                  </div>
                </button>

                {/* Missed Yesterday */}
                <button
                  onClick={() => {
                    setSelectedMessageType("missed_yesterday");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "missed_yesterday"
                      ? "ring-2 ring-offset-2 ring-orange-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "missed_yesterday"
                      ? "bg-gradient-to-br from-orange-500 to-orange-600 text-white"
                      : "bg-orange-100 text-orange-700 border border-orange-300"
                  }`}
                >
                  <div className="font-bold text-sm">Missed Yesterday</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.missed_yesterday}
                  </div>
                </button>

                {/* Missed This Month */}
                <button
                  onClick={() => {
                    setSelectedMessageType("missed_this_month");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "missed_this_month"
                      ? "ring-2 ring-offset-2 ring-pink-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "missed_this_month"
                      ? "bg-gradient-to-br from-pink-500 to-pink-600 text-white"
                      : "bg-pink-100 text-pink-700 border border-pink-300"
                  }`}
                >
                  <div className="font-bold text-sm">Missed Month</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.missed_this_month}
                  </div>
                </button>

                {/* Attended Yesterday */}
                <button
                  onClick={() => {
                    setSelectedMessageType("attended_yesterday");
                    setCurrentPage(1);
                  }}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "attended_yesterday"
                      ? "ring-2 ring-offset-2 ring-teal-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "attended_yesterday"
                      ? "bg-gradient-to-br from-teal-500 to-teal-600 text-white"
                      : "bg-teal-100 text-teal-700 border border-teal-300"
                  }`}
                >
                  <div className="font-bold text-sm">Thank You</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.attended_yesterday}
                  </div>
                </button>
              </div>
            </div>

            {/* Summary Section */}
            <div className="mb-4 grid grid-cols-3 gap-3">
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <p className="text-xs text-green-600 font-medium">SENT</p>
                <p className="text-lg font-bold text-green-700">
                  {sentMessages.filter((m) => m.status === "sent").length}
                </p>
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-xs text-blue-600 font-medium">TO BE SENT</p>
                <p className="text-lg font-bold text-blue-700">
                  {sentMessages.filter((m) => m.status === "scheduled").length}
                </p>
              </div>
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                <p className="text-xs text-slate-600 font-medium">TOTAL</p>
                <p className="text-lg font-bold text-slate-700">
                  {sentMessages.length}
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Status
                    </th>
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Customer
                    </th>
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Reason
                    </th>
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Type
                    </th>
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Date & Time
                    </th>
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMessages.length === 0 ? (
                    <tr>
                      <td
                        colSpan="6"
                        className="py-8 text-center text-slate-500"
                      >
                        {searchQuery
                          ? "No messages found matching your search"
                          : "No messages yet"}
                      </td>
                    </tr>
                  ) : (
                    filteredMessages.map((message) => {
                      const typeInfo = getMessageTypeInfo(message.message_type);
                      const TypeIcon = typeInfo.icon;
                      const isSent = message.status === "sent";
                      const isScheduled = message.status === "scheduled";

                      // Get the appropriate date/time
                      let dateTime = null;
                      let dateTimeLabel = "";

                      if (isSent && message.sent_at) {
                        dateTime = new Date(message.sent_at);
                        dateTimeLabel = "Sent";
                      } else if (isScheduled && message.send_at) {
                        dateTime = new Date(message.send_at);
                        dateTimeLabel = "Scheduled for";
                      }

                      return (
                        <tr
                          key={message.message_id}
                          className={`border-b border-slate-100 hover:bg-slate-50 ${
                            isScheduled ? "bg-blue-50" : ""
                          }`}
                        >
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                                isSent
                                  ? "bg-green-100 text-green-700"
                                  : "bg-blue-100 text-blue-700"
                              }`}
                            >
                              {isSent ? (
                                <>
                                  <CheckCircleIcon className="w-3 h-3 mr-1" />
                                  Sent
                                </>
                              ) : (
                                <>
                                  <ClockIcon className="w-3 h-3 mr-1" />
                                  Scheduled
                                </>
                              )}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <div>
                              <p className="font-medium text-slate-800">
                                {message.customer_name || "Unknown"}
                              </p>
                              <p className="text-sm text-slate-500">
                                {message.customer_phone}
                              </p>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div className="text-sm">
                              <p className="font-medium text-slate-700">
                                {message.reason}
                              </p>
                              {isScheduled && message.time_until_send && (
                                <p className="text-xs text-blue-600">
                                  {message.time_until_send.split(".")[0]} left
                                </p>
                              )}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${typeInfo.color}`}
                            >
                              <TypeIcon className="w-3 h-3 mr-1" />
                              {typeInfo.name}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <div className="text-sm">
                              {dateTime ? (
                                <>
                                  <p className="text-slate-800">
                                    {dateTime.toLocaleDateString()}
                                  </p>
                                  <p className="text-slate-500">
                                    {dateTime.toLocaleTimeString()}
                                  </p>
                                  <p className="text-xs text-slate-400 mt-1">
                                    {dateTimeLabel}
                                  </p>
                                </>
                              ) : (
                                <span className="text-slate-400">—</span>
                              )}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div className="text-sm">
                              <p className="text-slate-600">
                                {message.language.toUpperCase()}
                              </p>
                              {message.template_data?.appointment_date && (
                                <p className="text-xs text-slate-500 mt-1">
                                  Appt: {message.template_data.appointment_date}
                                </p>
                              )}
                              {message.content_preview && (
                                <p className="text-xs text-slate-400 truncate mt-1">
                                  {message.content_preview.substring(0, 40)}...
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {allFilteredMessages.length > RECORDS_PER_PAGE && (
              <div className="mt-4 flex items-center justify-between">
                <div className="text-sm text-slate-600">
                  Showing {startIndex + 1} -{" "}
                  {Math.min(endIndex, allFilteredMessages.length)} of{" "}
                  {allFilteredMessages.length} records
                </div>
                <div className="flex gap-2 items-center">
                  <button
                    onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                  >
                    ← Previous
                  </button>

                  <div className="flex gap-1">
                    {pageNumbers.map((page, index) => {
                      if (page === "...") {
                        return (
                          <span
                            key={`ellipsis-${index}`}
                            className="px-2 py-1 text-slate-500"
                          >
                            ...
                          </span>
                        );
                      }
                      return (
                        <button
                          key={page}
                          onClick={() => setCurrentPage(page)}
                          className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                            currentPage === page
                              ? "bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-lg ring-2 ring-offset-2 ring-primary-300"
                              : "border border-slate-300 text-slate-700 hover:bg-slate-50"
                          }`}
                        >
                          {page}
                        </button>
                      );
                    })}
                  </div>

                  <button
                    onClick={() =>
                      setCurrentPage(Math.min(totalPages, currentPage + 1))
                    }
                    disabled={currentPage === totalPages}
                    className="px-3 py-1 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}
          </motion.div>
        )}

        {activeTab === "templates" && (
          <motion.div
            key="templates"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {/* Testing Lab Section */}
            <div className="card bg-gradient-to-br from-blue-50 to-indigo-50 border-2 border-blue-200">
              <div className="mb-4">
                <h3 className="text-xl font-bold text-slate-800 mb-2 flex items-center">
                  <SparklesIcon className="w-6 h-6 mr-2 text-blue-600" />
                  Testing Lab
                </h3>
                <p className="text-sm text-slate-600">
                  Test any template with any phone number before sending to
                  customers
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {/* Template Selector */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    📋 Select Template
                  </label>
                  <select
                    value={selectedTemplate}
                    onChange={(e) => setSelectedTemplate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
                  >
                    <option value="">Choose template...</option>
                    {Object.entries(messageTemplates).map(([id, data]) => (
                      <option key={id} value={id}>
                        {data.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Language Selector */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    🌐 Language
                  </label>
                  <select
                    value={selectedLanguage}
                    onChange={(e) => setSelectedLanguage(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
                  >
                    <option value="ar">🇸🇦 Arabic</option>
                    <option value="en">🇬🇧 English</option>
                    <option value="fr">🇫🇷 French</option>
                  </select>
                </div>

                {/* Phone Number Input */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    📱 Phone Number
                  </label>
                  <input
                    type="text"
                    placeholder="+961 XX XXX XXXX"
                    value={testPhoneNumber}
                    onChange={(e) => setTestPhoneNumber(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                {/* Send Test Button */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    &nbsp;
                  </label>
                  <button
                    onClick={async () => {
                      if (!selectedTemplate) {
                        toast.error("Please select a template");
                        return;
                      }
                      if (!testPhoneNumber) {
                        toast.error("Please enter a phone number");
                        return;
                      }

                      setSendingTest(true);
                      try {
                        const baseURL =
                          window.location.hostname === "localhost" ||
                          window.location.hostname === "127.0.0.1"
                            ? "http://localhost:8003"
                            : window.location.origin;

                        const response = await fetch(
                          `${baseURL}/api/smart-messaging/send-test-template`,
                          {
                            method: "POST",
                            headers: {
                              "Content-Type": "application/json",
                            },
                            body: JSON.stringify({
                              template_id: selectedTemplate,
                              phone_number: testPhoneNumber,
                              language: selectedLanguage,
                            }),
                          }
                        );

                        const result = await response.json();

                        if (result.success) {
                          toast.success(
                            `✅ Template sent to ${testPhoneNumber}!`
                          );
                        } else {
                          toast.error(`❌ ${result.error || "Failed to send"}`);
                        }
                      } catch (error) {
                        console.error("Error sending test:", error);
                        toast.error("Failed to send test message");
                      } finally {
                        setSendingTest(false);
                      }
                    }}
                    disabled={
                      sendingTest || !selectedTemplate || !testPhoneNumber
                    }
                    className={`w-full py-2 px-4 rounded-lg font-medium transition-all ${
                      sendingTest || !selectedTemplate || !testPhoneNumber
                        ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                        : "bg-blue-600 text-white hover:bg-blue-700 shadow-lg hover:shadow-xl"
                    }`}
                  >
                    {sendingTest ? "📤 Sending..." : "📤 Send Test"}
                  </button>
                </div>
              </div>

              {/* Preview Section */}
              {selectedTemplate && (
                <div className="mt-4 p-4 bg-white rounded-lg border border-slate-200">
                  <p className="text-xs font-semibold text-slate-600 mb-2">
                    PREVIEW:
                  </p>
                  <div className="text-sm text-slate-700 whitespace-pre-wrap font-mono">
                    {messageTemplates[selectedTemplate]?.[selectedLanguage] ||
                      "No content"}
                  </div>
                </div>
              )}
            </div>

            {/* Template Status Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(messageTemplates).map(
                ([templateId, templateData]) => {
                  const Icon = getTemplateIcon(templateId);
                  const color = getTemplateColor(templateId);
                  const isActive = templateStates[templateId] !== false; // Default to true

                  return (
                    <div
                      key={templateId}
                      className="card hover:shadow-lg transition-shadow"
                    >
                      {/* Header with Icon */}
                      <div className="flex items-center space-x-3 mb-4">
                        <div
                          className={`p-3 rounded-lg bg-gradient-to-r ${color}`}
                        >
                          <Icon className="w-6 h-6 text-white" />
                        </div>
                        <div className="flex-1">
                          <h3 className="font-bold text-slate-800">
                            {templateData.name}
                          </h3>
                          <p className="text-xs text-slate-500">
                            {templateData.description}
                          </p>
                        </div>
                      </div>

                      {/* Stats */}
                      <div className="mb-4 p-3 bg-slate-50 rounded-lg">
                        <div className="flex justify-between items-center">
                          <span className="text-sm text-slate-600">
                            Messages Sent
                          </span>
                          <span className="text-lg font-bold text-slate-800">
                            {stats.by_type?.[templateId]?.sent || 0}
                          </span>
                        </div>
                      </div>

                      {/* Active/Inactive Switch */}
                      <div className="flex items-center justify-between p-4 bg-gradient-to-r from-slate-50 to-slate-100 rounded-lg border-2 border-slate-200">
                        <div>
                          <p className="font-semibold text-slate-800">
                            {isActive ? "✅ Active" : "⏸️ Inactive"}
                          </p>
                          <p className="text-xs text-slate-600">
                            {isActive
                              ? "Periodic messages enabled"
                              : "Periodic messages disabled"}
                          </p>
                        </div>
                        <button
                          onClick={() => {
                            setTemplateStates((prev) => ({
                              ...prev,
                              [templateId]: !isActive,
                            }));
                            toast.success(
                              isActive
                                ? `${templateData.name} deactivated`
                                : `${templateData.name} activated`
                            );
                          }}
                          className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                            isActive
                              ? "bg-green-500 focus:ring-green-500"
                              : "bg-slate-300 focus:ring-slate-400"
                          }`}
                        >
                          <span
                            className={`inline-block h-6 w-6 transform rounded-full bg-white transition-transform ${
                              isActive ? "translate-x-7" : "translate-x-1"
                            }`}
                          />
                        </button>
                      </div>
                    </div>
                  );
                }
              )}
            </div>
          </motion.div>
        )}

        {activeTab === "mappings" && (
          <motion.div
            key="mappings"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="card"
          >
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6">
              <div>
                <h3 className="text-xl font-bold text-slate-800 flex items-center space-x-2">
                  <Squares2X2Icon className="w-6 h-6 text-indigo-500" />
                  <span>Service-Template Mappings</span>
                </h3>
                <p className="text-sm text-slate-600 mt-1">
                  Configure which message templates are enabled for each service
                </p>
              </div>
              <button
                onClick={handleSaveServiceMappings}
                className="mt-4 sm:mt-0 px-6 py-2 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-lg font-medium hover:from-primary-600 hover:to-primary-700 transition-all shadow-lg flex items-center space-x-2"
              >
                <CheckCircleIcon className="w-5 h-5" />
                <span>Save Mappings</span>
              </button>
            </div>

            {/* Empty State for Services */}
            {availableServices.length === 0 ? (
              <div className="text-center py-12">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-slate-100 rounded-full mb-4">
                  <Squares2X2Icon className="w-8 h-8 text-slate-400" />
                </div>
                <h4 className="text-lg font-semibold text-slate-800 mb-2">No Services Found</h4>
                <p className="text-slate-600">Services will appear here once configured.</p>
              </div>
            ) : (
              /* Grid Table */
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-slate-100">
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 border-b border-slate-200 sticky left-0 bg-slate-100 z-10">
                        Service Name
                      </th>
                      {availableTemplates.map((template) => (
                        <th
                          key={template.id}
                          className="text-center py-3 px-3 font-semibold text-slate-700 border-b border-slate-200 min-w-[100px]"
                        >
                          <div className="flex flex-col items-center">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium mb-1 ${
                              getMessageTypeInfo(template.id).color
                            }`}>
                              {template.name || getMessageTypeInfo(template.id).name}
                            </span>
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {availableServices.map((service, index) => (
                      <tr
                        key={service.service_id}
                        className={`${index % 2 === 0 ? 'bg-white' : 'bg-slate-50'} hover:bg-primary-50 transition-colors`}
                      >
                        <td className="py-3 px-4 border-b border-slate-200 sticky left-0 bg-inherit z-10">
                          <div>
                            <p className="font-medium text-slate-800">{service.service_name}</p>
                          </div>
                        </td>
                        {availableTemplates.map((template) => {
                          const isEnabled = serviceMappings[service.service_id]?.templates?.[template.id] ?? true;
                          return (
                            <td
                              key={template.id}
                              className="text-center py-3 px-3 border-b border-slate-200"
                            >
                              <button
                                onClick={() => handleToggleServiceTemplate(service.service_id, template.id)}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                                  isEnabled
                                    ? "bg-green-500 focus:ring-green-500"
                                    : "bg-slate-300 focus:ring-slate-400"
                                }`}
                              >
                                <span
                                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                    isEnabled ? "translate-x-6" : "translate-x-1"
                                  }`}
                                />
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Legend */}
            <div className="mt-6 p-4 bg-slate-50 rounded-lg border border-slate-200">
              <p className="text-sm font-semibold text-slate-700 mb-2">Legend:</p>
              <div className="flex flex-wrap gap-4">
                <div className="flex items-center space-x-2">
                  <div className="w-8 h-4 bg-green-500 rounded-full"></div>
                  <span className="text-sm text-slate-600">Enabled - Messages will be sent</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-8 h-4 bg-slate-300 rounded-full"></div>
                  <span className="text-sm text-slate-600">Disabled - Messages will not be sent</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default SmartMessaging;
