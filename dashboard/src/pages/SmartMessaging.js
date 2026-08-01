import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  MagnifyingGlassIcon,
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
  Squares2X2Icon,
  InboxIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  ArrowPathRoundedSquareIcon,
  HeartIcon,
  CalendarDaysIcon,
  StarIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { apiUrl } from "../utils/apiBaseUrl";
import { authFetch } from '../utils/authFetch';

/**
 * Titles shown on template cards, test-template dropdown, and mappings table.
 * Matches WhatsApp/Meta template names from config/montymobile_templates.json
 * (missed_yesterday → outbound name sent_day_after_missed_appointment).
 */
const SYSTEM_TEMPLATE_LABELS = {
  reminder_24h: {
    title: "reminder_24h",
    subtitle:
      "24h before tomorrow's appointments. Body: customer_name, date, time, branch, service.",
  },
  thank_you_message_sent_after_session: {
    title: "thank_you_message_sent_after_session",
    subtitle:
      "Same day after Done visit, N hours after slot. Body: customer_name. Star replies → Star ratings.",
  },
  session_feedback: {
    title: "session_feedback",
    subtitle: "Next day after Done visit. Body: customer_name. Meta rating buttons.",
  },
  missed_yesterday: {
    title: "sent_day_after_missed_appointment",
    subtitle: "Internal queue id: missed_yesterday. Day after missed appointment. Body: customer_name.",
  },
  sent_17_days_after_last_session_new: {
    title: "sent_17_days_after_last_session_new",
    subtitle: "17 days after last Done session. Body: customer_name, branch_name, service_name.",
  },
  sent_for_pause: {
    title: "sent_for_pause",
    subtitle: "Paused BOC / end-of-month campaign. Body: customer_name.",
  },
  whatsapp_lead_no_booking: {
    title: "whatsapp_lead_no_booking",
    subtitle: "Manual campaign: WhatsApp lead, no CRM booking. Body vars per Meta (often 0).",
  },
};

function getSystemTemplateLabel(templateId) {
  return SYSTEM_TEMPLATE_LABELS[templateId] || null;
}

function getTemplateCardDisplay(templateId, templateData) {
  const sys = getSystemTemplateLabel(templateId);
  if (sys) {
    return { title: sys.title, description: sys.subtitle };
  }
  return {
    title: templateData?.name || templateId,
    description: templateData?.description || "",
  };
}

function getTemplateSelectLabel(templateId, templateData) {
  const sys = getSystemTemplateLabel(templateId);
  if (sys) return sys.title;
  return (templateData && templateData.name) || templateId;
}

const localISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

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
  const [templateSchedules, setTemplateSchedules] = useState({});
  const [savingTemplateSchedule, setSavingTemplateSchedule] = useState(null);

  // NEW: Filter and pagination state
  const [selectedMessageType, setSelectedMessageType] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const RECORDS_PER_PAGE = 20;

  // NEW: Lazy loading state
  const [messageCounts, setMessageCounts] = useState({});
  const [loadingCategory, setLoadingCategory] = useState(null);
  const [loadedCategories, setLoadedCategories] = useState(new Set());
  // Customer list from source-of-truth API (per category)
  const [categoryCustomers, setCategoryCustomers] = useState({});

  // NEW: Smart Messages control states
  const [smartMessagingEnabled, setSmartMessagingEnabled] = useState(true);
  const [previewBeforeSend, setPreviewBeforeSend] = useState(true);
  const [pendingMessages, setPendingMessages] = useState([]);
  const [selectedPendingMessages, setSelectedPendingMessages] = useState([]);
  const [serviceMappings, setServiceMappings] = useState({});
  const [availableServices, setAvailableServices] = useState([]);
  const [availableTemplates, setAvailableTemplates] = useState([]);

  // NEW: Edit modals state
  const [editingScheduledMessage, setEditingScheduledMessage] = useState(null);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [showCreateTemplateModal, setShowCreateTemplateModal] = useState(false);
  const [newTemplate, setNewTemplate] = useState({
    id: "",
    name: "",
    description: "",
    ar: "",
    en: "",
    fr: ""
  });
  const [savingScheduledEdit, setSavingScheduledEdit] = useState(false);
  const [viewingMessage, setViewingMessage] = useState(null);
  const [viewingMessageEdit, setViewingMessageEdit] = useState({ content: "", sendTime: "" });
  const [savingViewEdit, setSavingViewEdit] = useState(false);
  const [collectingCounts, setCollectingCounts] = useState(false);

  // Send test template (phone + template; language from saved user prefs unless overridden)
  const [testPhone, setTestPhone] = useState("");
  const [testTemplateId, setTestTemplateId] = useState("");
  const [testLangMode, setTestLangMode] = useState("auto");
  const [testSendLoading, setTestSendLoading] = useState(false);
  const [testLangPreview, setTestLangPreview] = useState(null);
  const [templateHeaderImageUrl, setTemplateHeaderImageUrl] = useState("");
  const [savingHeaderUrl, setSavingHeaderUrl] = useState(false);

  const [sessionStarRatings, setSessionStarRatings] = useState([]);
  const [sessionStarRatingsLoading, setSessionStarRatingsLoading] = useState(false);
  const [sessionRatingsTick, setSessionRatingsTick] = useState(0);

  // Manual BOC "paused appointments" campaign (Meta / internal id: sent_for_pause)
  const [pausedFromDate, setPausedFromDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return localISODate(d);
  });
  const [pausedToDate, setPausedToDate] = useState(() => localISODate(new Date()));
  const [pausedServiceIds, setPausedServiceIds] = useState([]);
  const [pausedPreviewLoading, setPausedPreviewLoading] = useState(false);
  const [pausedSendLoading, setPausedSendLoading] = useState(false);
  const [pausedRecipients, setPausedRecipients] = useState([]);
  const [pausedCampaignError, setPausedCampaignError] = useState(null);
  const [pausedPlaceholdersHelp, setPausedPlaceholdersHelp] = useState(null);

  // Manual WhatsApp leads: chatted in Firestore, no BOC customer file, no appointments (whatsapp_lead_no_booking)
  const [leadFromDate, setLeadFromDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return localISODate(d);
  });
  const [leadToDate, setLeadToDate] = useState(() => localISODate(new Date()));
  const [leadServiceIds, setLeadServiceIds] = useState([]);
  const [leadPreviewLoading, setLeadPreviewLoading] = useState(false);
  const [leadSendLoading, setLeadSendLoading] = useState(false);
  const [leadRecipients, setLeadRecipients] = useState([]);
  const [leadCampaignError, setLeadCampaignError] = useState(null);

  // Fetch real data from API
  useEffect(() => {
    fetchSmartMessagingData();
    fetchSmartMessagingSettings();
    fetchPendingMessages();
    fetchServiceMappings();
    fetchTemplateSchedules();
  }, []);

  useEffect(() => {
    if (activeTab !== "sessionRatings") return;
    let cancelled = false;
    const run = async () => {
      setSessionStarRatingsLoading(true);
      try {
        const res = await authFetch(
          apiUrl("/api/smart-messaging/post-session-feedback-ratings?limit=400")
        );
        const data = await res.json();
        if (cancelled) return;
        if (data.success) {
          setSessionStarRatings(Array.isArray(data.ratings) ? data.ratings : []);
        } else {
          toast.error(data.error || "Failed to load star ratings");
        }
      } catch {
        if (!cancelled) toast.error("Failed to load star ratings");
      } finally {
        if (!cancelled) setSessionStarRatingsLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [activeTab, sessionRatingsTick]);

  useEffect(() => {
    const ids = Object.keys(messageTemplates || {}).sort();
    if (ids.length === 0) return;
    setTestTemplateId((prev) => (prev && messageTemplates[prev] ? prev : ids[0]));
  }, [messageTemplates]);

  const fetchTestLangPreview = async () => {
    const p = testPhone.trim();
    if (!p) {
      setTestLangPreview(null);
      return;
    }
    try {
      const res = await authFetch(
        apiUrl(`/api/smart-messaging/user-language?phone=${encodeURIComponent(p)}`)
      );
      const data = await res.json();
      if (data.success) {
        setTestLangPreview(data);
      } else {
        setTestLangPreview(null);
      }
    } catch {
      setTestLangPreview(null);
    }
  };

  const handlePausedPreview = async () => {
    if (!pausedFromDate || !pausedToDate) {
      toast.error("Choose from and to dates");
      return;
    }
    setPausedPreviewLoading(true);
    setPausedCampaignError(null);
    setPausedPlaceholdersHelp(null);
    try {
      const body = {
        from_date: pausedFromDate,
        to_date: pausedToDate,
        service_ids: pausedServiceIds.length ? pausedServiceIds : [],
      };
      const res = await authFetch(apiUrl("/api/smart-messaging/campaigns/missed-paused/preview"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        setPausedRecipients(data.recipients || []);
        setPausedPlaceholdersHelp(data.placeholders_help || null);
        toast.success(`Found ${data.count ?? (data.recipients || []).length} recipient(s)`);
      } else {
        setPausedRecipients([]);
        setPausedPlaceholdersHelp(null);
        const msg = data.error || "Preview failed";
        setPausedCampaignError(msg);
        toast.error(msg);
      }
    } catch (e) {
      console.error(e);
      setPausedRecipients([]);
      setPausedPlaceholdersHelp(null);
      toast.error("Preview failed");
    } finally {
      setPausedPreviewLoading(false);
    }
  };

  const handlePausedSend = async () => {
    if (!pausedFromDate || !pausedToDate) {
      toast.error("Choose from and to dates");
      return;
    }
    if (!pausedRecipients.length) {
      toast.error("Load recipients with Preview first");
      return;
    }
    if (
      !window.confirm(
        `Send the Missed Paused Appointment message to ${pausedRecipients.length} phone number(s) now?`
      )
    ) {
      return;
    }
    setPausedSendLoading(true);
    try {
      const res = await authFetch(apiUrl("/api/smart-messaging/campaigns/missed-paused/send"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filters: {
            from_date: pausedFromDate,
            to_date: pausedToDate,
            service_ids: pausedServiceIds.length ? pausedServiceIds : [],
          },
          send_mode: "send_now",
        }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(
          `Sent: ${data.sent_count ?? 0}, failed: ${data.failed_count ?? 0}${
            data.campaign_id ? ` (campaign ${data.campaign_id})` : ""
          }`
        );
        setPausedRecipients([]);
      } else {
        toast.error(data.error || "Send failed");
      }
    } catch (e) {
      console.error(e);
      toast.error("Send failed");
    } finally {
      setPausedSendLoading(false);
    }
  };

  const handleLeadPreview = async () => {
    if (!leadFromDate || !leadToDate) {
      toast.error("Choose from and to dates");
      return;
    }
    setLeadPreviewLoading(true);
    setLeadCampaignError(null);
    try {
      const body = {
        from_date: leadFromDate,
        to_date: leadToDate,
        service_ids: leadServiceIds.length ? leadServiceIds : [],
      };
      const res = await authFetch(apiUrl("/api/smart-messaging/campaigns/whatsapp-leads-no-crm/preview"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        setLeadRecipients(data.recipients || []);
        toast.success(`Found ${data.count ?? (data.recipients || []).length} recipient(s)`);
      } else {
        setLeadRecipients([]);
        const msg = data.error || "Preview failed";
        setLeadCampaignError(msg);
        toast.error(msg);
      }
    } catch (e) {
      console.error(e);
      setLeadRecipients([]);
      toast.error("Preview failed");
    } finally {
      setLeadPreviewLoading(false);
    }
  };

  const handleLeadSend = async () => {
    if (!leadFromDate || !leadToDate) {
      toast.error("Choose from and to dates");
      return;
    }
    if (!leadRecipients.length) {
      toast.error("Load recipients with Preview first");
      return;
    }
    if (
      !window.confirm(
        `Send the WhatsApp lead (no CRM) message to ${leadRecipients.length} phone number(s) now?`
      )
    ) {
      return;
    }
    setLeadSendLoading(true);
    try {
      const res = await authFetch(apiUrl("/api/smart-messaging/campaigns/whatsapp-leads-no-crm/send"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filters: {
            from_date: leadFromDate,
            to_date: leadToDate,
            service_ids: leadServiceIds.length ? leadServiceIds : [],
          },
          send_mode: "send_now",
        }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(
          `Sent: ${data.sent_count ?? 0}, failed: ${data.failed_count ?? 0}${
            data.campaign_id ? ` (campaign ${data.campaign_id})` : ""
          }`
        );
        setLeadRecipients([]);
      } else {
        toast.error(data.error || "Send failed");
      }
    } catch (e) {
      console.error(e);
      toast.error("Send failed");
    } finally {
      setLeadSendLoading(false);
    }
  };

  const handleSendTestTemplate = async () => {
    if (!testPhone.trim() || !testTemplateId) {
      toast.error("Enter phone number and select a template");
      return;
    }
    setTestSendLoading(true);
    try {
      const payload = {
        phone_number: testPhone.trim(),
        template_id: testTemplateId,
      };
      if (testLangMode !== "auto") {
        payload.language = testLangMode;
      }
      const headerUrl = templateHeaderImageUrl.trim();
      if (headerUrl) {
        payload.header_image_url = headerUrl;
      }
      const res = await authFetch(apiUrl("/api/smart-messaging/send-test-template"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      let result;
      try {
        result = await res.json();
      } catch {
        toast.error(`Send test failed (HTTP ${res.status})`);
        return;
      }
      if (!res.ok) {
        const errBase =
          result?.detail || result?.error || `Send test failed (HTTP ${res.status})`;
        const errExtra = [result?.monty_message, result?.outbound_template_name]
          .filter(Boolean)
          .join(" — ");
        toast.error(errExtra ? `${errBase} — ${errExtra}` : errBase);
        return;
      }
      if (result.success) {
        const src =
          result.language_source === "manual"
            ? "manual"
            : result.language_source === "saved"
              ? "saved for this number"
              : "default (no saved language)";
        let successMsg = `Sent — user language: ${result.user_language} (${src}) → WhatsApp template language: ${result.template_language}`;
        if (result.vary_test_payload_applied) {
          successMsg +=
            "\nتمت إضافة علامة وقت صغيرة على أحد الحقول حتى واتساب يقبل تكرار التجربة (ميتا أحياناً يحجب نفس النص 100%). عطّلها من الـ API بـ vary_test_payload: false إذا بدك نص مطابق حرفياً.";
        }
        if (result.placeholder_source) {
          successMsg += `\nData: ${result.placeholder_source}`;
        }
        if (Array.isArray(result.placeholder_warnings) && result.placeholder_warnings.length) {
          successMsg += `\n${result.placeholder_warnings.join(" ")}`;
        }
        if (result.test_template_note) {
          successMsg += `\n\n${result.test_template_note}`;
        }
        toast.success(successMsg, {
          duration:
            result.test_template_note || (result.placeholder_warnings && result.placeholder_warnings.length)
              ? 10000
              : 5000,
        });
      } else {
        const parts = [
          result.error || "Failed to send test",
          result.monty_message,
          result.outbound_template_name
            ? `outbound name: ${result.outbound_template_name}`
            : null,
        ].filter(Boolean);
        let msg = parts.join(" — ");
        if (msg.length > 380) msg = `${msg.slice(0, 377)}…`;
        toast.error(msg);
      }
    } catch (e) {
      console.error(e);
      toast.error("Failed to send test");
    } finally {
      setTestSendLoading(false);
    }
  };

  const handleSaveTemplateHeaderImage = async () => {
    setSavingHeaderUrl(true);
    try {
      const res = await authFetch(apiUrl("/api/smart-messaging/settings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ templateHeaderImageUrl: templateHeaderImageUrl.trim() }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success("Template header image URL saved");
        if (data.settings?.templateHeaderImageUrl != null) {
          setTemplateHeaderImageUrl(data.settings.templateHeaderImageUrl);
        }
      } else {
        toast.error(data.error || "Save failed");
      }
    } catch (e) {
      console.error(e);
      toast.error("Save failed");
    } finally {
      setSavingHeaderUrl(false);
    }
  };

  // Fetch smart messaging settings (global toggle, preview mode)
  const fetchSmartMessagingSettings = async () => {
    try {
      const response = await authFetch(apiUrl("/api/smart-messaging/settings"));
      const result = await response.json();
      if (result.success) {
        setSmartMessagingEnabled(result.settings?.enabled ?? true);
        setPreviewBeforeSend(result.settings?.previewBeforeSend ?? true);
        setTemplateHeaderImageUrl(result.settings?.templateHeaderImageUrl ?? "");
      }
    } catch (error) {
      console.error("Error fetching smart messaging settings:", error);
    }
  };

  // Fetch pending approval messages
  const fetchPendingMessages = async () => {
    try {
      const response = await authFetch(apiUrl("/api/smart-messaging/preview-queue?status=pending_approval"));
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
        authFetch(apiUrl("/api/smart-messaging/service-mappings")),
        authFetch(apiUrl("/api/smart-messaging/services")),
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

  const fetchTemplateSchedules = async () => {
    try {
      const response = await authFetch(apiUrl("/api/smart-messaging/template-schedules"));
      const result = await response.json();
      if (result.success) {
        setTemplateSchedules(result.schedules || {});
      }
    } catch (error) {
      console.error("Error fetching template schedules:", error);
    }
  };

  // Toggle smart messaging on/off
  const handleToggleSmartMessaging = async () => {
    try {
      const response = await authFetch(apiUrl("/api/smart-messaging/toggle"), {
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
      const response = await authFetch(apiUrl("/api/smart-messaging/settings"), {
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
      const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${messageId}/approve`), {
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
      const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${messageId}/reject`), {
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
      const response = await authFetch(apiUrl("/api/smart-messaging/preview-queue/batch-approve"), {
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
      const response = await authFetch(apiUrl("/api/smart-messaging/preview-queue/batch-reject"), {
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
        await authFetch(apiUrl(`/api/smart-messaging/service-mappings/${serviceId}`), {
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

  const handleTemplateScheduleChange = (templateId, field, value) => {
    setTemplateSchedules((prev) => ({
      ...prev,
      [templateId]: {
        ...(prev[templateId] || {}),
        [field]: value,
      },
    }));
  };

  const handleSaveTemplateSchedule = async (templateId) => {
    const schedule = templateSchedules[templateId];
    if (!schedule) return;

    setSavingTemplateSchedule(templateId);
    try {
      const payload = {
        enabled: !!schedule.enabled,
        sendTime: schedule.sendTime || "15:00",
        timezone: schedule.timezone || "Asia/Beirut",
      };
      if (templateId === "thank_you_message_sent_after_session" && schedule.delayHours != null) {
        const n = Number(schedule.delayHours);
        if (!Number.isNaN(n)) {
          payload.delayHours = n;
        }
      }
      const response = await authFetch(apiUrl(`/api/smart-messaging/template-schedules/${templateId}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (result.success) {
        toast.success("Template schedule saved");
        fetchTemplateSchedules();
      } else {
        toast.error(result.error || "Failed to save schedule");
      }
    } catch (error) {
      console.error("Error saving template schedule:", error);
      toast.error("Failed to save schedule");
    } finally {
      setSavingTemplateSchedule(null);
    }
  };

  // View a message's full content (Eye icon) - for scheduled messages also allows inline edit
  const handleViewMessage = async (message) => {
    let fullContent = message.full_content || message.content_preview || "";

    // If we don't have full content, fetch it
    if (!message.full_content && message.message_id) {
      try {
        const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${message.message_id}`));
        const result = await response.json();
        if (result.success && result.message) {
          fullContent = result.message.rendered_content || result.message.content || fullContent;
        }
      } catch (error) {
        console.error("Error fetching message details:", error);
      }
    }

    const isScheduled = message.status === "scheduled" || message.status === "pending_approval";
    setViewingMessage({ ...message, fullContent });
    setViewingMessageEdit({
      content: fullContent,
      sendTime: message.send_at ? new Date(message.send_at).toISOString().slice(0, 16) : ""
    });
  };

  // Save edits from the View modal (Eye modal) - for scheduled messages
  const handleSaveViewModalEdit = async () => {
    if (!viewingMessage || !viewingMessage.message_id) return;
    setSavingViewEdit(true);
    try {
      const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${viewingMessage.message_id}/edit`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rendered_content: viewingMessageEdit.content,
          scheduled_send_time: viewingMessageEdit.sendTime
        })
      });
      const result = await response.json();
      if (result.success) {
        toast.success("Message updated!");
        setViewingMessage({ ...viewingMessage, fullContent: viewingMessageEdit.content, send_at: viewingMessageEdit.sendTime });
        fetchSmartMessagingData();
        setViewingMessage(null);
      } else {
        toast.error(result.error || "Failed to update message");
      }
    } catch (error) {
      console.error("Error saving message edit:", error);
      toast.error("Failed to update message");
    } finally {
      setSavingViewEdit(false);
    }
  };

  // Edit a scheduled message - use full_content if available, otherwise fetch
  const handleEditScheduledMessage = async (message) => {
    // First, try to use full_content from the message object (already loaded)
    let fullContent = message.full_content || message.content_preview || "";

    // If we don't have full content, fetch it from the API
    if (!message.full_content) {
      try {
        const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${message.message_id}`));
        const result = await response.json();

        if (result.success && result.message) {
          fullContent = result.message.rendered_content || result.message.content || fullContent;
        }
      } catch (error) {
        console.error("Error fetching message details:", error);
      }
    }

    setEditingScheduledMessage({
      ...message,
      editedContent: fullContent,
      editedSendTime: message.send_at ? new Date(message.send_at).toISOString().slice(0, 16) : ""
    });
  };

  // Save edited scheduled message
  const handleSaveScheduledMessageEdit = async () => {
    if (!editingScheduledMessage) return;

    setSavingScheduledEdit(true);
    try {
      const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${editingScheduledMessage.message_id}/edit`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rendered_content: editingScheduledMessage.editedContent,
          scheduled_send_time: editingScheduledMessage.editedSendTime
        })
      });

      const result = await response.json();
      if (result.success) {
        toast.success("Message updated successfully!");
        setEditingScheduledMessage(null);
        fetchSmartMessagingData();
      } else {
        toast.error(result.error || "Failed to update message");
      }
    } catch (error) {
      console.error("Error saving scheduled message edit:", error);
      toast.error("Failed to save changes");
    } finally {
      setSavingScheduledEdit(false);
    }
  };

  // Cancel a scheduled message
  const handleCancelScheduledMessage = async (messageId) => {
    if (!window.confirm("Are you sure you want to cancel this scheduled message?")) return;

    try {
      const response = await authFetch(apiUrl(`/api/smart-messaging/preview-queue/${messageId}/reject`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Cancelled by user" })
      });

      const result = await response.json();
      if (result.success) {
        toast.success("Scheduled message cancelled");
        fetchSmartMessagingData();
      } else {
        toast.error(result.error || "Failed to cancel message");
      }
    } catch (error) {
      console.error("Error cancelling message:", error);
      toast.error("Failed to cancel message");
    }
  };

  // Open template editor
  const handleEditTemplate = (templateId) => {
    const template = messageTemplates[templateId];
    if (template) {
      setEditingTemplate({
        id: templateId,
        name: template.name,
        description: template.description,
        ar: template.ar || "",
        en: template.en || "",
        fr: template.fr || ""
      });
    }
  };

  // Save template edits
  const handleSaveTemplateEdit = async () => {
    if (!editingTemplate) return;

    setSavingTemplate(editingTemplate.id);
    try {
      const response = await authFetch(apiUrl(`/api/smart-messaging/templates/${editingTemplate.id}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ar: editingTemplate.ar,
          en: editingTemplate.en,
          fr: editingTemplate.fr,
          name: editingTemplate.name,
          description: editingTemplate.description
        })
      });

      const result = await response.json();
      if (result.success) {
        toast.success("Template saved successfully!");
        setEditingTemplate(null);
        fetchSmartMessagingData();
      } else {
        toast.error(result.error || "Failed to save template");
      }
    } catch (error) {
      console.error("Error saving template:", error);
      toast.error("Failed to save template");
    } finally {
      setSavingTemplate(null);
    }
  };

  // Create new template
  const handleCreateTemplate = async () => {
    if (!newTemplate.id || !newTemplate.name) {
      toast.error("Template ID and name are required");
      return;
    }

    // Validate ID format (lowercase, underscores only)
    const idPattern = /^[a-z][a-z0-9_]*$/;
    if (!idPattern.test(newTemplate.id)) {
      toast.error("Template ID must start with a letter and contain only lowercase letters, numbers, and underscores");
      return;
    }

    if (messageTemplates[newTemplate.id]) {
      toast.error("A template with this ID already exists");
      return;
    }

    setSavingTemplate("new");
    try {
      const response = await authFetch(apiUrl(`/api/smart-messaging/templates/${newTemplate.id}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ar: newTemplate.ar || "",
          en: newTemplate.en || "",
          fr: newTemplate.fr || "",
          name: newTemplate.name,
          description: newTemplate.description,
          isNew: true
        })
      });

      const result = await response.json();
      if (result.success) {
        toast.success("Template created successfully!");
        setShowCreateTemplateModal(false);
        setNewTemplate({ id: "", name: "", description: "", ar: "", en: "", fr: "" });
        fetchSmartMessagingData();
      } else {
        toast.error(result.error || "Failed to create template");
      }
    } catch (error) {
      console.error("Error creating template:", error);
      toast.error("Failed to create template");
    } finally {
      setSavingTemplate(null);
    }
  };

  // Delete a custom template
  const handleDeleteTemplate = async (templateId) => {
    if (!window.confirm(`Are you sure you want to delete the template "${messageTemplates[templateId]?.name}"?`)) {
      return;
    }

    try {
      const response = await authFetch(apiUrl(`/api/smart-messaging/templates/${templateId}`), {
        method: "DELETE"
      });

      const result = await response.json();
      if (result.success) {
        toast.success("Template deleted successfully!");
        fetchSmartMessagingData();
      } else {
        toast.error(result.error || "Failed to delete template");
      }
    } catch (error) {
      console.error("Error deleting template:", error);
      toast.error("Failed to delete template");
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
    // Only full-page spinner on first load; refetches after edits would hide the whole
    // page (including "Send test template") and feel like sends "stopped working".
    const showFullPageLoader =
      !messageTemplates || Object.keys(messageTemplates).length === 0;
    try {
      if (showFullPageLoader) {
        setLoading(true);
      }

      const fetchJsonSafely = async (path) => {
        try {
          const response = await authFetch(apiUrl(path));
          return await response.json();
        } catch (error) {
          console.error(`Error fetching ${path}:`, error);
          return null;
        }
      };

      const [statusResult, countsResult, templatesResult] = await Promise.all([
        fetchJsonSafely("/api/smart-messaging/status"),
        fetchJsonSafely("/api/smart-messaging/counts"),
        fetchJsonSafely("/api/smart-messaging/templates")
      ]);

      if (statusResult?.success) {
        setSchedulerStatus(statusResult);
      } else if (statusResult) {
        console.warn("Failed to fetch scheduler status:", statusResult.error);
      }

      // ✅ LAZY LOADING: Fetch only counts initially (fast)
      if (countsResult?.success) {
        setMessageCounts(countsResult.counts || {});
      } else if (countsResult) {
        console.warn("Failed to fetch message counts:", countsResult.error);
      }

      // Clear messages and customer lists - loaded when category is selected
      setSentMessages([]);
      setLoadedCategories(new Set());
      setCategoryCustomers({});

      // Fetch templates
      if (templatesResult?.success) {
        setMessageTemplates(templatesResult.templates);
        // Initialize edited templates with current values
        setEditedTemplates(
          JSON.parse(JSON.stringify(templatesResult.templates))
        );
        // selectedLanguage is now a single string, not per-template
        // Already initialized to "ar" in useState
      } else if (templatesResult) {
        console.warn("Failed to fetch templates:", templatesResult.error);
      }

      fetchTemplateSchedules();
    } catch (error) {
      console.error("Error fetching smart messaging data:", error);
      toast.error("Failed to load smart messaging data");
    } finally {
      if (showFullPageLoader) {
        setLoading(false);
      }
    }
  };

  // Collect scheduled messages from appointments API, then refresh counts
  const handleCollectAndRefresh = async () => {
    try {
      setCollectingCounts(true);
      const response = await authFetch(apiUrl("/api/smart-messaging/collect-scheduled"), {
        method: "POST",
      });
      const result = await response.json();
      if (result.success) {
        toast.success(`Collected ${result.total_messages || 0} messages to be sent`);
        await fetchSmartMessagingData();
      } else {
        toast.error(result.error || "Failed to collect");
      }
    } catch (error) {
      console.error("Error collecting:", error);
      toast.error("Failed to collect scheduled messages");
    } finally {
      setCollectingCounts(false);
    }
  };

  // ✅ Fetch customer list from source-of-truth API (counts match this list)
  const fetchMessagesForCategory = async (category) => {
    if (category === "all") {
      setCategoryCustomers(prev => ({ ...prev, all: [] }));
      setLoadedCategories(prev => new Set([...prev, "all"]));
      return;
    }
    if (loadedCategories.has(category) && loadingCategory !== category) {
      return;
    }

    try {
      setLoadingCategory(category);

      const response = await authFetch(
        apiUrl(`/api/smart-messaging/customers-by-category?category=${encodeURIComponent(category)}`)
      );
      const result = await response.json();

      if (result.success) {
        const customers = result.customers || [];
        setCategoryCustomers(prev => ({ ...prev, [category]: customers }));
        setLoadedCategories(prev => new Set([...prev, category]));
      } else {
        setCategoryCustomers(prev => ({ ...prev, [category]: [] }));
        setLoadedCategories(prev => new Set([...prev, category]));
      }
    } catch (error) {
      console.error(`Error fetching customers for ${category}:`, error);
      toast.error(`Failed to load ${category} customers`);
      setCategoryCustomers(prev => ({ ...prev, [category]: [] }));
      setLoadedCategories(prev => new Set([...prev, category]));
    } finally {
      setLoadingCategory(null);
    }
  };

  // ✅ LAZY LOADING: Handle category selection
  const handleCategorySelect = (category) => {
    setSelectedMessageType(category);
    setCurrentPage(1);
    fetchMessagesForCategory(category);
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

      const response = await authFetch(apiUrl(`/api/smart-messaging/templates/${templateId}`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ar: editedTemplates[templateId].ar,
          en: editedTemplates[templateId].en,
          fr: editedTemplates[templateId].fr,
        }),
      });

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

  // Date-range filter helper based on message type
  const isMessageInDateRange = (message, messageType) => {
    const now = new Date();
    // Use local date components (not toISOString which converts to UTC)
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(yesterday.getDate()).padStart(2, "0")}`;
    const startOfMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    const startOfNextMonthStr = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, "0")}-${String(nextMonth.getDate()).padStart(2, "0")}`;

    // Get the send/sent date (YYYY-MM-DD) for this message
    const sendDateStr = (message.send_at || message.sent_at || message.scheduled_for || "").substring(0, 10) || null;
    // Get appointment date from template_data
    const appointmentDate = message.template_data?.appointment_date || null;

    // Get send time as Date object (used for 24h reminder)
    const sendTime = new Date(message.send_at || message.sent_at || message.created_at || message.scheduled_at);

    switch (messageType) {
      case "reminder_24h":
        // Show messages where send_at is within ±24h from now
        if (isNaN(sendTime.getTime())) return true;
        const past24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        const next24h = new Date(now.getTime() + 24 * 60 * 60 * 1000);
        return sendTime >= past24h && sendTime <= next24h;
      case "thank_you_message_sent_after_session":
        // Show messages scheduled for today only
        if (!sendDateStr) return true;
        return sendDateStr === todayStr;
      case "session_feedback":
        if (!sendDateStr) return true;
        return sendDateStr === todayStr;
      case "missed_yesterday":
        // Show yesterday's missed appointments
        return appointmentDate === yesterdayStr || sendDateStr === yesterdayStr;
      case "sent_17_days_after_last_session_new":
        // Show 17-day followups scheduled within current month
        return sendDateStr >= startOfMonthStr && sendDateStr < startOfNextMonthStr;
      default:
        return true;
    }
  };

  // Filter messages based on search query, message type, AND date range
  const allFilteredMessages = sentMessages
    .filter((message) => {
      // Filter by type
      if (
        selectedMessageType !== "all" &&
        message.message_type !== selectedMessageType
      ) {
        return false;
      }

      // Filter by date range based on message type
      // For "all" tab: apply each message's own category date filter
      // For specific tab: apply that category's date filter
      const typeToCheck = selectedMessageType === "all" ? message.message_type : selectedMessageType;
      if (!isMessageInDateRange(message, typeToCheck)) {
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

  // When a single category is selected, show customer list from source-of-truth API
  const customersForTable = selectedMessageType && selectedMessageType !== "all"
    ? (categoryCustomers[selectedMessageType] || [])
    : [];
  const tableRows = customersForTable.length > 0
    ? customersForTable.map((row, idx) => ({
        message_id: row.appointment_id ? `cust_${row.appointment_id}_${idx}` : `cust_${row.phone}_${idx}`,
        customer_name: row.customer_name,
        customer_phone: row.phone,
        reason: row.reason,
        message_type: row.type,
        status: row.action_state === "pending" ? "scheduled" : row.action_state,
        date: row.date,
        time: row.time,
        details: row.details,
        template_data: { appointment_date: row.date },
      }))
    : allFilteredMessages;

  // Pagination
  const totalPages = Math.ceil(tableRows.length / RECORDS_PER_PAGE);
  const startIndex = (currentPage - 1) * RECORDS_PER_PAGE;
  const endIndex = startIndex + RECORDS_PER_PAGE;
  const filteredMessages = tableRows.slice(startIndex, endIndex);

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

  // ✅ Counts from API (source of truth); never show negative
  const messageTypesCounts = {
    all: Math.max(0, Object.values(messageCounts).reduce((sum, count) => sum + (Number(count) || 0), 0)),
    reminder_24h: Math.max(0, Number(messageCounts.reminder_24h) || 0),
    thank_you_message_sent_after_session: Math.max(0, Number(messageCounts.thank_you_message_sent_after_session) || 0),
    session_feedback: Math.max(0, Number(messageCounts.session_feedback) || 0),
    sent_17_days_after_last_session_new: Math.max(0, Number(messageCounts.sent_17_days_after_last_session_new) || 0),
    missed_yesterday: Math.max(0, Number(messageCounts.missed_yesterday) || 0),
  };

  const getMessageTypeInfo = (type) => {
    const types = {
      reminder_24h: {
        name: "reminder_24h",
        color: "bg-blue-100 text-blue-700",
        icon: ClockIcon,
      },
      thank_you_message_sent_after_session: {
        name: "thank_you_message_sent_after_session",
        color: "bg-green-100 text-green-700",
        icon: CheckCircleIcon,
      },
      session_feedback: {
        name: "session_feedback",
        color: "bg-rose-100 text-rose-700",
        icon: HeartIcon,
      },
      sent_17_days_after_last_session_new: {
        name: "sent_17_days_after_last_session_new",
        color: "bg-indigo-100 text-indigo-700",
        icon: SparklesIcon,
      },
      missed_yesterday: {
        name: "sent_day_after_missed_appointment",
        color: "bg-orange-100 text-orange-700",
        icon: ExclamationTriangleIcon,
      },
    };
    // Return default info for custom templates
    return types[type] || {
      name: type ? type.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()) : "Custom",
      color: "bg-violet-100 text-violet-700",
      icon: EnvelopeIcon,
    };
  };

  const getTemplateIcon = (templateId) => {
    const icons = {
      reminder_24h: ClockIcon,
      thank_you_message_sent_after_session: CheckCircleIcon,
      session_feedback: HeartIcon,
      sent_17_days_after_last_session_new: SparklesIcon,
      missed_yesterday: ExclamationTriangleIcon,
    };
    // Return default icon for custom templates
    return icons[templateId] || EnvelopeIcon;
  };

  const getTemplateColor = (templateId) => {
    const colors = {
      reminder_24h: "from-blue-500 to-cyan-500",
      thank_you_message_sent_after_session: "from-green-500 to-emerald-500",
      session_feedback: "from-rose-500 to-pink-600",
      sent_17_days_after_last_session_new: "from-indigo-500 to-purple-500",
      missed_yesterday: "from-orange-400 to-orange-600",
    };
    // Return a purple gradient for custom templates
    return colors[templateId] || "from-violet-500 to-purple-600";
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

      {/* Test send: real WhatsApp template to one number, language from user prefs unless overridden */}
      <motion.div
        id="smart-messaging-send-test"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="card border-2 border-indigo-100 bg-gradient-to-br from-white to-indigo-50/40 shadow-md scroll-mt-24"
      >
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <PaperAirplaneIcon className="w-6 h-6 text-indigo-600" />
              Send test template
            </h2>
            <p className="text-sm text-slate-600 mt-1 max-w-2xl">
              Enter a WhatsApp number that exists in CRM with a real booking. Test sends fill name, date, time,
              branch, and service from the live API (next appointment / customer list) — same idea as production,
              not dummy text. Language follows the user&apos;s saved preference unless you override ar / en / fr.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Phone number</label>
            <input
              type="text"
              value={testPhone}
              onChange={(e) => setTestPhone(e.target.value)}
              onBlur={fetchTestLangPreview}
              placeholder="+961..."
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
            />
            {testLangPreview?.success && testLangMode === "auto" && (
              <p className="text-xs text-slate-600 mt-1">
                Saved language:{" "}
                <span className="font-semibold text-slate-800">{testLangPreview.language}</span>
                {testLangPreview.language_source === "default" && (
                  <span className="text-amber-700"> (no record — default ar)</span>
                )}
                {testLangPreview.normalized_phone ? (
                  <span className="block text-slate-500 mt-0.5">
                    Normalized: {testLangPreview.normalized_phone}
                  </span>
                ) : null}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Template</label>
            <select
              value={testTemplateId}
              onChange={(e) => setTestTemplateId(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
            >
              {Object.keys(messageTemplates || {})
                .sort()
                .map((id) => (
                  <option key={id} value={id}>
                    {getTemplateSelectLabel(id, messageTemplates[id])}
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Language</label>
            <select
              value={testLangMode}
              onChange={(e) => {
                setTestLangMode(e.target.value);
                if (e.target.value !== "auto") setTestLangPreview(null);
              }}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
            >
              <option value="auto">Auto (from user / number)</option>
              <option value="ar">Arabic (ar)</option>
              <option value="en">English (en)</option>
              <option value="fr">French (fr)</option>
              <option value="franco">Franco → template ar</option>
            </select>
          </div>
          <div>
            <button
              type="button"
              onClick={handleSendTestTemplate}
              disabled={testSendLoading || !testPhone.trim() || !testTemplateId}
              className="w-full px-4 py-2.5 rounded-lg font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {testSendLoading ? (
                <>
                  <span className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  Sending…
                </>
              ) : (
                <>
                  <PaperAirplaneIcon className="w-5 h-5" />
                  Send test
                </>
              )}
            </button>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-indigo-100">
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Template header image URL (required if Meta templates use an image header)
          </label>
          <p className="text-xs text-slate-500 mb-2 max-w-3xl">
            Same public HTTPS image as in WhatsApp Manager for your template header. Saving applies to test
            sends and production template sends. Alternatively set server env{" "}
            <code className="text-slate-700 bg-slate-100 px-1 rounded">MONTY_TEMPLATE_HEADER_IMAGE_URL</code>.
          </p>
          <div className="flex flex-col sm:flex-row gap-2 max-w-4xl">
            <input
              type="url"
              value={templateHeaderImageUrl}
              onChange={(e) => setTemplateHeaderImageUrl(e.target.value)}
              placeholder="https://example.com/your-approved-header.png"
              className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={handleSaveTemplateHeaderImage}
              disabled={savingHeaderUrl}
              className="px-4 py-2 rounded-lg font-medium text-white bg-slate-700 hover:bg-slate-800 disabled:bg-slate-400 whitespace-nowrap"
            >
              {savingHeaderUrl ? "Saving…" : "Save URL"}
            </button>
          </div>
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
      <div className="flex flex-wrap gap-1 bg-slate-100 p-1 rounded-lg">
        <button
          onClick={() => setActiveTab("sent")}
          className={`flex-1 min-w-[120px] py-2 px-4 rounded-md font-medium transition-all ${
            activeTab === "sent"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Sent Messages
        </button>
        <button
          onClick={() => setActiveTab("templates")}
          className={`flex-1 min-w-[120px] py-2 px-4 rounded-md font-medium transition-all ${
            activeTab === "templates"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Message Templates
        </button>
        <button
          onClick={() => setActiveTab("mappings")}
          className={`flex-1 min-w-[140px] py-2 px-4 rounded-md font-medium transition-all ${
            activeTab === "mappings"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Service Mappings
        </button>
        <button
          onClick={() => setActiveTab("sessionRatings")}
          className={`flex-1 min-w-[140px] py-2 px-2 sm:px-4 rounded-md font-medium transition-all text-sm sm:text-base ${
            activeTab === "sessionRatings"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Star ratings
        </button>
        <button
          onClick={() => setActiveTab("pausedCampaign")}
          className={`flex-1 py-2 px-2 sm:px-4 rounded-md font-medium transition-all text-sm sm:text-base ${
            activeTab === "pausedCampaign"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          Paused (BOC)
        </button>
        <button
          onClick={() => setActiveTab("leadNoCrmCampaign")}
          className={`flex-1 py-2 px-2 sm:px-4 rounded-md font-medium transition-all text-sm sm:text-base ${
            activeTab === "leadNoCrmCampaign"
              ? "bg-white text-primary-600 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          WhatsApp leads
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
            {/* Search Bar + Refresh Counts */}
            <div className="mb-4 flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by customer name, phone, or message type..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
              <button
                onClick={handleCollectAndRefresh}
                disabled={collectingCounts}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed font-medium flex items-center justify-center gap-2 whitespace-nowrap"
              >
                {collectingCounts ? (
                  <>
                    <span className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    Collecting...
                  </>
                ) : (
                  <>
                    <ArrowPathRoundedSquareIcon className="w-5 h-5" />
                    Refresh Counts
                  </>
                )}
              </button>
            </div>

            {/* Message Type Filter (Colored Buttons) */}
            <div className="mb-4">
              <p className="text-xs font-semibold text-slate-700 mb-3">
                FILTER BY MESSAGE TYPE:
              </p>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                {/* All Button */}
                <button
                  onClick={() => handleCategorySelect("all")}
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

                {/* Meta / internal: reminder_24h */}
                <button
                  onClick={() => handleCategorySelect("reminder_24h")}
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
                  <div className="font-mono text-xs font-bold leading-tight break-all px-0.5">
                    reminder_24h
                  </div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.reminder_24h}
                  </div>
                </button>

                {/* Same-day stars (Meta: thank_you_message_sent_after_session) */}
                <button
                  onClick={() => handleCategorySelect("thank_you_message_sent_after_session")}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "thank_you_message_sent_after_session"
                      ? "ring-2 ring-offset-2 ring-green-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "thank_you_message_sent_after_session"
                      ? "bg-gradient-to-br from-green-500 to-green-600 text-white"
                      : "bg-green-100 text-green-700 border border-green-300"
                  }`}
                >
                  <div className="font-mono text-[10px] sm:text-xs font-bold leading-tight break-all px-0.5">
                    thank_you_message_sent_after_session
                  </div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.thank_you_message_sent_after_session}
                  </div>
                </button>

                {/* Meta template name = internal id: session_feedback */}
                <button
                  onClick={() => handleCategorySelect("session_feedback")}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "session_feedback"
                      ? "ring-2 ring-offset-2 ring-rose-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "session_feedback"
                      ? "bg-gradient-to-br from-rose-500 to-pink-600 text-white"
                      : "bg-rose-100 text-rose-700 border border-rose-300"
                  }`}
                >
                  <div className="font-mono text-xs font-bold leading-tight break-all px-0.5">
                    session_feedback
                  </div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.session_feedback}
                  </div>
                </button>

                {/* 17-day follow-up (Meta: sent_17_days_after_last_session_new) */}
                <button
                  onClick={() => handleCategorySelect("sent_17_days_after_last_session_new")}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "sent_17_days_after_last_session_new"
                      ? "ring-2 ring-offset-2 ring-indigo-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "sent_17_days_after_last_session_new"
                      ? "bg-gradient-to-br from-indigo-500 to-indigo-600 text-white"
                      : "bg-indigo-100 text-indigo-700 border border-indigo-300"
                  }`}
                >
                  <div className="font-mono text-xs font-bold leading-tight break-all px-0.5">
                    sent_17_days_after_last_session_new
                  </div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.sent_17_days_after_last_session_new}
                  </div>
                </button>

                {/* Outbound Meta name; internal id missed_yesterday */}
                <button
                  onClick={() => handleCategorySelect("missed_yesterday")}
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
                  <div className="font-mono text-[10px] sm:text-xs font-bold leading-tight break-all px-0.5">
                    sent_day_after_missed_appointment
                  </div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.missed_yesterday}
                  </div>
                </button>
              </div>
            </div>

            {/* Summary Section - reflects selected category */}
            <div className="mb-4 grid grid-cols-3 gap-3">
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <p className="text-xs text-green-600 font-medium">SENT</p>
                <p className="text-lg font-bold text-green-700">
                  {tableRows.filter((m) => m.status === "sent" || m.status === "would_send").length}
                </p>
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-xs text-blue-600 font-medium">TO BE SENT</p>
                <p className="text-lg font-bold text-blue-700">
                  {tableRows.filter((m) => m.status === "scheduled").length}
                </p>
              </div>
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                <p className="text-xs text-slate-600 font-medium">TOTAL</p>
                <p className="text-lg font-bold text-slate-700">
                  {tableRows.length}
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
                      Template
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
                    <th className="text-left py-3 px-4 font-medium text-slate-700">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {loadingCategory ? (
                    <tr>
                      <td
                        colSpan="7"
                        className="py-8 text-center text-slate-500"
                      >
                        <div className="flex items-center justify-center gap-2">
                          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary-500"></div>
                          Loading {loadingCategory.replace(/_/g, ' ')} messages...
                        </div>
                      </td>
                    </tr>
                  ) : filteredMessages.length === 0 ? (
                    <tr>
                      <td
                        colSpan="7"
                        className="py-8 text-center text-slate-500"
                      >
                        {searchQuery
                          ? "No messages found matching your search"
                          : selectedMessageType === "all"
                            ? "Select a category to view the customer list"
                            : !loadedCategories.has(selectedMessageType)
                              ? "Click a category to load the list"
                              : "No customers in this category"}
                      </td>
                    </tr>
                  ) : (
                    filteredMessages.map((message) => {
                      const typeInfo = getMessageTypeInfo(message.message_type);
                      const TypeIcon = typeInfo.icon;
                      const isSent = message.status === "sent" || message.status === "would_send";
                      const isScheduled = message.status === "scheduled";

                      // Get the appropriate date/time (customer rows use date + time)
                      let dateTime = null;
                      let dateTimeLabel = "";

                      if (message.date && message.time) {
                        dateTime = new Date(`${message.date}T${message.time}`);
                        dateTimeLabel = "Appointment";
                      } else if (isSent && message.sent_at) {
                        dateTime = new Date(message.sent_at);
                        dateTimeLabel = message.status === "would_send" ? "Would send" : "Sent";
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
                                message.status === "would_send"
                                  ? "bg-amber-100 text-amber-700"
                                  : isSent
                                    ? "bg-green-100 text-green-700"
                                    : "bg-blue-100 text-blue-700"
                              }`}
                            >
                              {message.status === "would_send" ? (
                                <>Would send</>
                              ) : isSent ? (
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
                              <p className="font-medium text-slate-700" title="Template used for this message">
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
                              {message.details ? (
                                <p className="text-slate-600">{message.details}</p>
                              ) : (
                                <>
                                  <p className="text-slate-600">
                                    {(message.language || "ar").toUpperCase()}
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
                                </>
                              )}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center space-x-1">
                              {/* View button - available for all messages */}
                              <button
                                onClick={() => handleViewMessage(message)}
                                className="p-1.5 text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                                title="View message"
                              >
                                <EyeIcon className="w-4 h-4" />
                              </button>
                              {/* Edit and Cancel - only for scheduled messages */}
                              {isScheduled && (
                                <>
                                  <button
                                    onClick={() => handleEditScheduledMessage(message)}
                                    className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                                    title="Edit message"
                                  >
                                    <PencilIcon className="w-4 h-4" />
                                  </button>
                                  <button
                                    onClick={() => handleCancelScheduledMessage(message.message_id)}
                                    className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                    title="Cancel message"
                                  >
                                    <XMarkIcon className="w-4 h-4" />
                                  </button>
                                </>
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
            <div className="rounded-lg border border-indigo-200 bg-indigo-50/80 px-4 py-3 text-sm text-slate-700">
              <span className="font-semibold text-slate-800">Feedback</span> (green card in Sent Messages): same{" "}
              <span className="font-medium">calendar day</span> as the appointment, sent{" "}
              <span className="font-medium">N hours after the slot</span> (set below on that card).{" "}
              <span className="font-semibold text-slate-800">Session Feedback</span> (next day): everyone who was{" "}
              <span className="font-medium">Done yesterday</span> gets one send at your{" "}
              <span className="font-medium">daily send time</span>. Star replies (1–5) are listed under the{" "}
              <span className="font-medium">Star ratings</span> tab. Star buttons need a WhatsApp template with
              quick replies approved in Meta.{" "}
              <a
                href="#smart-messaging-send-test"
                className="text-indigo-700 font-semibold underline underline-offset-2 hover:text-indigo-900"
              >
                Send test template
              </a>{" "}
              — top of this page (scroll up).
            </div>
            {/* Header with Create Button */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-slate-800">Message Templates</h3>
                <p className="text-sm text-slate-600">Manage and customize your message templates</p>
              </div>
              <button
                onClick={() => setShowCreateTemplateModal(true)}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors flex items-center space-x-2 shadow-lg"
              >
                <PlusIcon className="w-5 h-5" />
                <span>Create Template</span>
              </button>
            </div>

            {/* Template Status Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(messageTemplates).map(([templateId, templateData]) => {
                  const cardDisplay = getTemplateCardDisplay(templateId, templateData);
                  const Icon = getTemplateIcon(templateId);
                  const color = getTemplateColor(templateId);
                  const scheduleConfig = {
                    enabled: true,
                    sendTime: "15:00",
                    timezone: "Asia/Beirut",
                    delayHours: 3,
                    ...(templateSchedules[templateId] || {}),
                  };
                  const isDailyTemplate = [
                    "reminder_24h",
                    "thank_you_message_sent_after_session",
                    "session_feedback",
                    "missed_yesterday",
                    "sent_17_days_after_last_session_new",
                  ].includes(templateId);
                  const isActive = isDailyTemplate ? scheduleConfig.enabled !== false : true;
                  // Check if this is a custom template (not one of the default ones)
                  const defaultTemplates = [
                    "reminder_24h",
                    "thank_you_message_sent_after_session",
                    "session_feedback",
                    "sent_17_days_after_last_session_new",
                    "missed_yesterday",
                  ];
                  const isCustomTemplate = !defaultTemplates.includes(templateId);

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
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-2">
                            <h3
                              className={`font-bold text-slate-800 break-all ${
                                getSystemTemplateLabel(templateId) ? "font-mono text-sm" : ""
                              }`}
                            >
                              {cardDisplay.title}
                            </h3>
                            {isCustomTemplate && (
                              <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded shrink-0">Custom</span>
                            )}
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {cardDisplay.description}
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

                      {/* Edit Button */}
                      <div className="mb-4">
                        <button
                          onClick={() => handleEditTemplate(templateId)}
                          className="w-full px-4 py-2 bg-blue-50 text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors flex items-center justify-center space-x-2"
                        >
                          <PencilIcon className="w-4 h-4" />
                          <span>Edit Template</span>
                        </button>
                      </div>

                      {isDailyTemplate ? (
                        <div className="p-4 bg-gradient-to-r from-slate-50 to-slate-100 rounded-lg border-2 border-slate-200 space-y-3">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="font-semibold text-slate-800">
                                {templateId === "thank_you_message_sent_after_session"
                                  ? isActive
                                    ? "✅ Feedback job enabled"
                                    : "⏸️ Feedback job disabled"
                                  : isActive
                                    ? "✅ Daily Job Enabled"
                                    : "⏸️ Daily Job Disabled"}
                              </p>
                              <p className="text-xs text-slate-600">Timezone: {scheduleConfig.timezone || "Asia/Beirut"}</p>
                            </div>
                            <button
                              onClick={() =>
                                handleTemplateScheduleChange(templateId, "enabled", !isActive)
                              }
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
                          {templateId === "thank_you_message_sent_after_session" ? (
                            <>
                              <div className="grid grid-cols-2 gap-2">
                                <div>
                                  <label className="block text-xs text-slate-600 mb-1">
                                    Hours after appointment
                                  </label>
                                  <input
                                    type="number"
                                    min="0.5"
                                    max="72"
                                    step="0.5"
                                    value={scheduleConfig.delayHours ?? 3}
                                    onChange={(e) =>
                                      handleTemplateScheduleChange(
                                        templateId,
                                        "delayHours",
                                        parseFloat(e.target.value) || 3
                                      )
                                    }
                                    className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-sm"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-slate-600 mb-1">Timezone</label>
                                  <input
                                    type="text"
                                    value={scheduleConfig.timezone || "Asia/Beirut"}
                                    onChange={(e) =>
                                      handleTemplateScheduleChange(templateId, "timezone", e.target.value)
                                    }
                                    className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-sm"
                                  />
                                </div>
                              </div>
                              <p className="text-xs text-slate-500 leading-relaxed">
                                Sends <span className="font-medium text-slate-700">same day</span> once the
                                delay has passed after the appointment slot. The scheduler checks every few
                                minutes (not the &quot;Send time&quot; field). For star buttons on WhatsApp,
                                your Meta template must include quick-reply buttons — the bot sends the
                                approved template payload.
                              </p>
                            </>
                          ) : (
                            <div className="grid grid-cols-2 gap-2">
                              <div>
                                <label className="block text-xs text-slate-600 mb-1">Send Time</label>
                                <input
                                  type="time"
                                  value={scheduleConfig.sendTime || "15:00"}
                                  onChange={(e) =>
                                    handleTemplateScheduleChange(templateId, "sendTime", e.target.value)
                                  }
                                  className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-slate-600 mb-1">Timezone</label>
                                <input
                                  type="text"
                                  value={scheduleConfig.timezone || "Asia/Beirut"}
                                  onChange={(e) =>
                                    handleTemplateScheduleChange(templateId, "timezone", e.target.value)
                                  }
                                  className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-sm"
                                />
                              </div>
                            </div>
                          )}
                          <button
                            onClick={() => handleSaveTemplateSchedule(templateId)}
                            disabled={savingTemplateSchedule === templateId}
                            className={`w-full px-3 py-2 rounded-lg text-sm font-medium ${
                              savingTemplateSchedule === templateId
                                ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                                : "bg-indigo-600 text-white hover:bg-indigo-700"
                            }`}
                          >
                            {savingTemplateSchedule === templateId ? "Saving..." : "Save Schedule"}
                          </button>
                        </div>
                      ) : (
                        <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
                          <p className="text-sm font-semibold text-slate-800">Manual Campaign Template</p>
                          <p className="text-xs text-slate-600 mt-1">
                            This template is used via Campaign Builder (Preview + Send Now/Schedule).
                          </p>
                        </div>
                      )}

                      {/* Delete Button for Custom Templates */}
                      {isCustomTemplate && (
                        <div className="mt-3">
                          <button
                            onClick={() => handleDeleteTemplate(templateId)}
                            className="w-full px-4 py-2 text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors flex items-center justify-center space-x-2 text-sm"
                          >
                            <TrashIcon className="w-4 h-4" />
                            <span>Delete Template</span>
                          </button>
                        </div>
                      )}
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
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium mb-1 max-w-[140px] text-center leading-tight ${
                              getMessageTypeInfo(template.id).color
                            }`}>
                              <span className="font-mono break-all">
                                {getTemplateSelectLabel(template.id, { name: template.name })}
                              </span>
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
              <p className="text-xs text-slate-500 mt-3">
                <span className="font-medium">Missed Paused Appointment</span> and{" "}
                <span className="font-medium">WhatsApp leads (no CRM)</span> bulk sends are{" "}
                <span className="font-medium">manual only</span> — use{" "}
                <span className="font-medium">Paused (BOC)</span> or{" "}
                <span className="font-medium">WhatsApp leads</span>.
              </p>
            </div>
          </motion.div>
        )}

        {activeTab === "pausedCampaign" && (
          <motion.div
            key="pausedCampaign"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="card space-y-6"
          >
            <div>
              <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                <CalendarDaysIcon className="w-7 h-7 text-violet-600" />
                Missed Paused Appointment (BOC)
              </h3>
              <p className="text-sm text-slate-600 mt-1 max-w-3xl">
                Load customers whose appointments were <span className="font-medium">paused</span> in BOC between
                two dates, optionally filter by service, then send the{" "}
                <span className="font-mono text-xs font-medium">sent_for_pause</span> template when{" "}
                <span className="font-medium">you</span> click Send. Nothing is sent automatically from this
                screen. Edit Arabic / English / French text under{" "}
                <span className="font-medium">Message Templates</span> on this page. Each user receives the
                version in their <span className="font-medium">saved language</span> (from chat); if unknown,
                Arabic is used.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">From date</label>
                <input
                  type="date"
                  value={pausedFromDate}
                  onChange={(e) => setPausedFromDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">To date</label>
                <input
                  type="date"
                  value={pausedToDate}
                  onChange={(e) => setPausedToDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={handlePausedPreview}
                  disabled={pausedPreviewLoading}
                  className="flex-1 px-4 py-2 rounded-lg bg-slate-700 text-white text-sm font-medium hover:bg-slate-800 disabled:bg-slate-400"
                >
                  {pausedPreviewLoading ? "Loading…" : "Preview list"}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-2">
                Services (empty = all services)
              </label>
              {availableServices.length === 0 ? (
                <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  No services in mappings yet. Add services under Service Mappings, or leave filters empty to
                  query all services via the API.
                </p>
              ) : (
                <div className="max-h-44 overflow-y-auto border border-slate-200 rounded-lg p-3 space-y-2 bg-slate-50">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={pausedServiceIds.length === 0}
                      onChange={() => setPausedServiceIds([])}
                    />
                    <span className="font-medium text-slate-800">All services</span>
                  </label>
                  <div className="border-t border-slate-200 pt-2 space-y-1">
                    {availableServices.map((s) => (
                      <label
                        key={s.service_id}
                        className="flex items-center gap-2 text-sm cursor-pointer hover:bg-white/80 rounded px-1"
                      >
                        <input
                          type="checkbox"
                          checked={pausedServiceIds.includes(s.service_id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setPausedServiceIds((prev) =>
                                [...new Set([...prev, s.service_id])].sort((a, b) => a - b)
                              );
                            } else {
                              setPausedServiceIds((prev) => prev.filter((id) => id !== s.service_id));
                            }
                          }}
                        />
                        <span>{s.service_name}</span>
                        <span className="text-slate-400 text-xs">#{s.service_id}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {pausedCampaignError && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {pausedCampaignError}
              </div>
            )}

            {pausedPlaceholdersHelp && (
              <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                <span className="font-semibold text-slate-700">Template placeholders</span> (use in{" "}
                <span className="font-medium">Message Templates</span> →{" "}
                <span className="font-mono text-xs font-medium">sent_for_pause</span>):{" "}
                <span className="font-mono whitespace-pre-wrap break-all">{pausedPlaceholdersHelp}</span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handlePausedSend}
                disabled={pausedSendLoading || pausedRecipients.length === 0}
                className="px-6 py-2.5 rounded-lg bg-violet-600 text-white font-semibold hover:bg-violet-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {pausedSendLoading ? (
                  <>
                    <span className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    Sending…
                  </>
                ) : (
                  <>
                    <PaperAirplaneIcon className="w-5 h-5" />
                    Send to {pausedRecipients.length || "…"} recipient(s)
                  </>
                )}
              </button>
              <span className="text-sm text-slate-500">
                Run <span className="font-medium">Preview list</span> first to load phones from BOC.
              </span>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-slate-100">
                  <tr>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Customer</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Phone</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Appointment</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Service</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Branch</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Appt ID</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Machine</th>
                  </tr>
                </thead>
                <tbody>
                  {pausedRecipients.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        No recipients loaded. Set dates (and optional services) and click Preview list.
                      </td>
                    </tr>
                  ) : (
                    pausedRecipients.map((r, idx) => (
                      <tr key={`${r.phone}-${idx}`} className={idx % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                        <td className="py-2 px-3">{r.customer_name}</td>
                        <td className="py-2 px-3 font-mono text-xs">{r.phone}</td>
                        <td className="py-2 px-3">
                          {r.appointment_date} {r.appointment_time}
                        </td>
                        <td className="py-2 px-3">{r.service_name}</td>
                        <td className="py-2 px-3">{r.branch_name}</td>
                        <td className="py-2 px-3 font-mono text-xs">{r.appointment_id ?? "—"}</td>
                        <td className="py-2 px-3">{r.machine_name ?? "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}

        {activeTab === "leadNoCrmCampaign" && (
          <motion.div
            key="leadNoCrmCampaign"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="card space-y-6"
          >
            <div>
              <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                <InboxIcon className="w-7 h-7 text-teal-600" />
                WhatsApp leads — no CRM file / no booking
              </h3>
              <p className="text-sm text-slate-600 mt-1 max-w-3xl">
                Lists numbers that <span className="font-medium">messaged the bot</span> (Firestore) in the
                date range, with <span className="font-medium">no customer record</span> in BOC and{" "}
                <span className="font-medium">no appointments</span>. Optional services: keeps users whose
                recent chat text <span className="font-medium">mentions</span> one of the selected service
                names (from Service Mappings).                 Sends template{" "}
                <span className="font-medium">whatsapp_lead_no_booking</span> only when you click Send — not
                automatic. Edit AR / EN / FR under <span className="font-medium">Message Templates</span>. Each
                user gets their <span className="font-medium">saved language</span>; if unknown, Arabic.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">From date</label>
                <input
                  type="date"
                  value={leadFromDate}
                  onChange={(e) => setLeadFromDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">To date</label>
                <input
                  type="date"
                  value={leadToDate}
                  onChange={(e) => setLeadToDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={handleLeadPreview}
                  disabled={leadPreviewLoading}
                  className="flex-1 px-4 py-2 rounded-lg bg-slate-700 text-white text-sm font-medium hover:bg-slate-800 disabled:bg-slate-400"
                >
                  {leadPreviewLoading ? "Loading…" : "Preview list"}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-2">
                Services (empty = all; if set, chat history must mention the service name)
              </label>
              {availableServices.length === 0 ? (
                <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  No services in mappings yet. Leave empty to include all qualifying leads, or add services
                  under Service Mappings to filter by mentioned service names in chat.
                </p>
              ) : (
                <div className="max-h-44 overflow-y-auto border border-slate-200 rounded-lg p-3 space-y-2 bg-slate-50">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={leadServiceIds.length === 0}
                      onChange={() => setLeadServiceIds([])}
                    />
                    <span className="font-medium text-slate-800">All (no service text filter)</span>
                  </label>
                  <div className="border-t border-slate-200 pt-2 space-y-1">
                    {availableServices.map((s) => (
                      <label
                        key={s.service_id}
                        className="flex items-center gap-2 text-sm cursor-pointer hover:bg-white/80 rounded px-1"
                      >
                        <input
                          type="checkbox"
                          checked={leadServiceIds.includes(s.service_id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setLeadServiceIds((prev) =>
                                [...new Set([...prev, s.service_id])].sort((a, b) => a - b)
                              );
                            } else {
                              setLeadServiceIds((prev) => prev.filter((id) => id !== s.service_id));
                            }
                          }}
                        />
                        <span>{s.service_name}</span>
                        <span className="text-slate-400 text-xs">#{s.service_id}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {leadCampaignError && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {leadCampaignError}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleLeadSend}
                disabled={leadSendLoading || leadRecipients.length === 0}
                className="px-6 py-2.5 rounded-lg bg-teal-600 text-white font-semibold hover:bg-teal-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {leadSendLoading ? (
                  <>
                    <span className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    Sending…
                  </>
                ) : (
                  <>
                    <PaperAirplaneIcon className="w-5 h-5" />
                    Send to {leadRecipients.length || "…"} recipient(s)
                  </>
                )}
              </button>
              <span className="text-sm text-slate-500">
                Run <span className="font-medium">Preview list</span> first (checks BOC + Firestore).
              </span>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-slate-100">
                  <tr>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Name</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Phone</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Last chat</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Messages</th>
                    <th className="text-left py-2 px-3 font-semibold text-slate-700">Preview</th>
                  </tr>
                </thead>
                <tbody>
                  {leadRecipients.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-slate-500">
                        No recipients loaded. Set dates (and optional service filters) and click Preview
                        list.
                      </td>
                    </tr>
                  ) : (
                    leadRecipients.map((r, idx) => (
                      <tr key={`${r.phone}-${idx}`} className={idx % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                        <td className="py-2 px-3">{r.customer_name}</td>
                        <td className="py-2 px-3 font-mono text-xs">{r.phone}</td>
                        <td className="py-2 px-3">{r.last_chat_date || "—"}</td>
                        <td className="py-2 px-3">{r.message_count ?? "—"}</td>
                        <td className="py-2 px-3 max-w-xs truncate" title={r.last_message_preview}>
                          {r.last_message_preview || "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}

        {activeTab === "sessionRatings" && (
          <motion.div
            key="sessionRatings"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="card space-y-4"
          >
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
              <div>
                <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                  <StarIcon className="w-7 h-7 text-amber-500" />
                  Feedback — star replies
                </h3>
                <p className="text-sm text-slate-600 mt-1 max-w-3xl">
                  After the <span className="font-medium">Feedback</span> smart template is sent (same day after the
                  session), customers can reply with <span className="font-medium">1–5</span> (or a quick-reply title
                  that starts with a digit). Replies are logged here.{" "}
                  Next-day Meta template <span className="font-mono text-xs font-medium">session_feedback</span> is separate from same-day Feedback.
                  Use <span className="font-medium">Open chat</span> to open Live Chat with that number searched.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSessionRatingsTick((t) => t + 1)}
                disabled={sessionStarRatingsLoading}
                className="shrink-0 px-4 py-2 rounded-lg bg-slate-700 text-white text-sm font-medium hover:bg-slate-800 disabled:bg-slate-400"
              >
                {sessionStarRatingsLoading ? "Loading…" : "Refresh"}
              </button>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-lg">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold text-slate-600 uppercase tracking-wide">
                  <tr>
                    <th className="py-2 px-3">When</th>
                    <th className="py-2 px-3">Phone / user</th>
                    <th className="py-2 px-3">Stars</th>
                    <th className="py-2 px-3">Reply</th>
                    <th className="py-2 px-3">Appointment</th>
                    <th className="py-2 px-3">Conversation</th>
                    <th className="py-2 px-3">Chat</th>
                  </tr>
                </thead>
                <tbody>
                  {sessionStarRatingsLoading && sessionStarRatings.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        Loading…
                      </td>
                    </tr>
                  ) : sessionStarRatings.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        No star ratings logged yet. They appear when users reply 1–5 after the Feedback template is
                        delivered.
                      </td>
                    </tr>
                  ) : (
                    sessionStarRatings.map((row, idx) => {
                      const uid = String(row.user_id || "").trim();
                      const digits = uid.replace(/\D/g, "");
                      const searchQ = digits || uid;
                      return (
                        <tr
                          key={`${row.timestamp || ""}-${uid}-${idx}`}
                          className={idx % 2 === 0 ? "bg-white" : "bg-slate-50"}
                        >
                          <td className="py-2 px-3 whitespace-nowrap text-slate-700">
                            {row.timestamp
                              ? new Date(row.timestamp).toLocaleString()
                              : "—"}
                          </td>
                          <td className="py-2 px-3 font-mono text-xs text-slate-800">{uid || "—"}</td>
                          <td className="py-2 px-3">
                            <span className="text-amber-600 font-semibold" title={`${row.stars} / 5`}>
                              {"⭐".repeat(Math.min(5, Math.max(1, Number(row.stars) || 0)))}
                            </span>
                            <span className="text-slate-500 ml-1">({row.stars ?? "—"}/5)</span>
                          </td>
                          <td className="py-2 px-3 max-w-[200px] truncate text-slate-600" title={row.raw_reply}>
                            {row.raw_reply || "—"}
                          </td>
                          <td className="py-2 px-3 font-mono text-xs">{row.appointment_id ?? "—"}</td>
                          <td className="py-2 px-3 font-mono text-xs max-w-[140px] truncate" title={row.conversation_id}>
                            {row.conversation_id || "—"}
                          </td>
                          <td className="py-2 px-3">
                            {searchQ ? (
                              <Link
                                to={`/live-chat?search=${encodeURIComponent(searchQ)}`}
                                className="text-primary-600 font-medium hover:underline"
                              >
                                Open chat
                              </Link>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* View Message Modal */}
      <AnimatePresence>
        {viewingMessage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            onClick={() => setViewingMessage(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-bold text-slate-800">Message Details</h3>
                  <button
                    onClick={() => setViewingMessage(null)}
                    className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    <XMarkIcon className="w-5 h-5 text-slate-500" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-4">
                {/* Status Badge */}
                <div className="flex items-center space-x-3">
                  <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                    viewingMessage.status === "would_send"
                      ? "bg-amber-100 text-amber-700"
                      : viewingMessage.status === "sent"
                        ? "bg-green-100 text-green-700"
                        : "bg-blue-100 text-blue-700"
                  }`}>
                    {viewingMessage.status === "would_send" ? (
                      <>Would send (dry-run)</>
                    ) : viewingMessage.status === "sent" ? (
                      <>
                        <CheckCircleIcon className="w-4 h-4 mr-1" />
                        Sent
                      </>
                    ) : (
                      <>
                        <ClockIcon className="w-4 h-4 mr-1" />
                        Scheduled
                      </>
                    )}
                  </span>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    getMessageTypeInfo(viewingMessage.message_type).color
                  }`}>
                    {getMessageTypeInfo(viewingMessage.message_type).name}
                  </span>
                </div>

                {/* Customer Info */}
                <div className="p-4 bg-slate-50 rounded-lg">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-slate-500 uppercase">Customer</p>
                      <p className="font-semibold text-slate-800">{viewingMessage.customer_name}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 uppercase">Phone</p>
                      <p className="font-medium text-slate-700">{viewingMessage.customer_phone}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 uppercase">Language</p>
                      <p className="font-medium text-slate-700">{viewingMessage.language?.toUpperCase()}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 uppercase">
                        {(viewingMessage.status === "sent" || viewingMessage.status === "would_send") ? "Sent At" : "Scheduled For"}
                      </p>
                      <p className="font-medium text-slate-700">
                        {(viewingMessage.status === "sent" || viewingMessage.status === "would_send") && viewingMessage.sent_at
                          ? new Date(viewingMessage.sent_at).toLocaleString()
                          : viewingMessage.send_at
                          ? new Date(viewingMessage.send_at).toLocaleString()
                          : "-"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Message Content - editable for scheduled, read-only for sent */}
                <div>
                  <p className="text-sm font-medium text-slate-700 mb-2">
                    {(viewingMessage.status === "scheduled" || viewingMessage.status === "pending_approval")
                      ? "Message (editable)"
                      : "Message Content"}
                  </p>
                  {(viewingMessage.status === "scheduled" || viewingMessage.status === "pending_approval") ? (
                    <textarea
                      value={viewingMessageEdit.content}
                      onChange={(e) => setViewingMessageEdit((prev) => ({ ...prev, content: e.target.value }))}
                      rows={8}
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono text-sm"
                      placeholder="Message content..."
                    />
                  ) : (
                    <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
                      <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans">
                        {viewingMessage.fullContent || viewingMessage.content_preview || "No content available"}
                      </pre>
                    </div>
                  )}
                </div>

                {/* Scheduled time - editable for scheduled messages */}
                {(viewingMessage.status === "scheduled" || viewingMessage.status === "pending_approval") && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">Scheduled Send Time</label>
                    <input
                      type="datetime-local"
                      value={viewingMessageEdit.sendTime}
                      onChange={(e) => setViewingMessageEdit((prev) => ({ ...prev, sendTime: e.target.value }))}
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                    />
                  </div>
                )}
              </div>

              <div className="p-6 border-t border-slate-200 flex justify-end space-x-3">
                {(viewingMessage.status === "scheduled" || viewingMessage.status === "pending_approval") && (
                  <button
                    onClick={handleSaveViewModalEdit}
                    disabled={savingViewEdit}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2 disabled:opacity-50"
                  >
                    <CheckIcon className="w-4 h-4" />
                    <span>{savingViewEdit ? "Saving..." : "Save Changes"}</span>
                  </button>
                )}
                <button
                  onClick={() => setViewingMessage(null)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Scheduled Message Modal */}
      <AnimatePresence>
        {editingScheduledMessage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            onClick={() => setEditingScheduledMessage(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-bold text-slate-800">Edit Scheduled Message</h3>
                  <button
                    onClick={() => setEditingScheduledMessage(null)}
                    className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    <XMarkIcon className="w-5 h-5 text-slate-500" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-4">
                {/* Customer Info */}
                <div className="p-4 bg-slate-50 rounded-lg">
                  <p className="text-sm text-slate-600">Customer</p>
                  <p className="font-semibold text-slate-800">{editingScheduledMessage.customer_name}</p>
                  <p className="text-sm text-slate-500">{editingScheduledMessage.customer_phone}</p>
                </div>

                {/* Scheduled Time */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Scheduled Send Time
                  </label>
                  <input
                    type="datetime-local"
                    value={editingScheduledMessage.editedSendTime}
                    onChange={(e) => setEditingScheduledMessage({
                      ...editingScheduledMessage,
                      editedSendTime: e.target.value
                    })}
                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                </div>

                {/* Message Content */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Message Content
                  </label>
                  <textarea
                    value={editingScheduledMessage.editedContent}
                    onChange={(e) => setEditingScheduledMessage({
                      ...editingScheduledMessage,
                      editedContent: e.target.value
                    })}
                    rows={8}
                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono text-sm"
                    placeholder="Enter message content..."
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    {editingScheduledMessage.editedContent?.length || 0} characters
                  </p>
                </div>
              </div>

              <div className="p-6 border-t border-slate-200 flex justify-end space-x-3">
                <button
                  onClick={() => setEditingScheduledMessage(null)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveScheduledMessageEdit}
                  disabled={savingScheduledEdit}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
                >
                  {savingScheduledEdit ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Template Modal */}
      <AnimatePresence>
        {editingTemplate && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            onClick={() => setEditingTemplate(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-bold text-slate-800">Edit Template: {editingTemplate.name}</h3>
                  <button
                    onClick={() => setEditingTemplate(null)}
                    className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    <XMarkIcon className="w-5 h-5 text-slate-500" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-6">
                {/* Template Info */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Template Name
                    </label>
                    <input
                      type="text"
                      value={editingTemplate.name}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, name: e.target.value })}
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Description
                    </label>
                    <input
                      type="text"
                      value={editingTemplate.description}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, description: e.target.value })}
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                </div>

                {/* Language Tabs */}
                <div className="space-y-4">
                  {/* Arabic */}
                  <div className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex items-center space-x-2 mb-3">
                      <span className="text-lg">Arabic</span>
                      <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">RTL</span>
                    </div>
                    <textarea
                      value={editingTemplate.ar}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, ar: e.target.value })}
                      rows={5}
                      dir="rtl"
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    />
                  </div>

                  {/* English */}
                  <div className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex items-center space-x-2 mb-3">
                      <span className="text-lg">English</span>
                    </div>
                    <textarea
                      value={editingTemplate.en}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, en: e.target.value })}
                      rows={5}
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    />
                  </div>

                  {/* French */}
                  <div className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex items-center space-x-2 mb-3">
                      <span className="text-lg">French</span>
                    </div>
                    <textarea
                      value={editingTemplate.fr}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, fr: e.target.value })}
                      rows={5}
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    />
                  </div>
                </div>

                {/* Placeholders Help */}
                <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <p className="text-sm font-semibold text-blue-800 mb-2">Available Placeholders:</p>
                  <div className="flex flex-wrap gap-2">
                    {["{customer_name}", "{appointment_date}", "{appointment_time}", "{branch_name}", "{service_name}", "{phone_number}", "{next_appointment_date}"].map((ph) => (
                      <code key={ph} className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">
                        {ph}
                      </code>
                    ))}
                  </div>
                </div>
              </div>

              <div className="p-6 border-t border-slate-200 flex justify-end space-x-3">
                <button
                  onClick={() => setEditingTemplate(null)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveTemplateEdit}
                  disabled={savingTemplate === editingTemplate.id}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
                >
                  {savingTemplate === editingTemplate.id ? "Saving..." : "Save Template"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create Template Modal */}
      <AnimatePresence>
        {showCreateTemplateModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            onClick={() => setShowCreateTemplateModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-bold text-slate-800">Create New Template</h3>
                  <button
                    onClick={() => setShowCreateTemplateModal(false)}
                    className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    <XMarkIcon className="w-5 h-5 text-slate-500" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-6">
                {/* Template Info */}
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Template ID <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={newTemplate.id}
                      onChange={(e) => setNewTemplate({ ...newTemplate, id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })}
                      placeholder="e.g., holidays_greeting"
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    />
                    <p className="text-xs text-slate-500 mt-1">Lowercase letters, numbers, underscores only</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Template Name <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={newTemplate.name}
                      onChange={(e) => setNewTemplate({ ...newTemplate, name: e.target.value })}
                      placeholder="e.g., Holidays Greeting"
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Description
                    </label>
                    <input
                      type="text"
                      value={newTemplate.description}
                      onChange={(e) => setNewTemplate({ ...newTemplate, description: e.target.value })}
                      placeholder="e.g., Sent during holidays"
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                </div>

                {/* Language Templates */}
                <div className="space-y-4">
                  {/* Arabic */}
                  <div className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex items-center space-x-2 mb-3">
                      <span className="text-lg">Arabic</span>
                      <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">RTL</span>
                    </div>
                    <textarea
                      value={newTemplate.ar}
                      onChange={(e) => setNewTemplate({ ...newTemplate, ar: e.target.value })}
                      rows={4}
                      dir="rtl"
                      placeholder="Enter Arabic message template..."
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    />
                  </div>

                  {/* English */}
                  <div className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex items-center space-x-2 mb-3">
                      <span className="text-lg">English</span>
                    </div>
                    <textarea
                      value={newTemplate.en}
                      onChange={(e) => setNewTemplate({ ...newTemplate, en: e.target.value })}
                      rows={4}
                      placeholder="Enter English message template..."
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    />
                  </div>

                  {/* French */}
                  <div className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex items-center space-x-2 mb-3">
                      <span className="text-lg">French</span>
                    </div>
                    <textarea
                      value={newTemplate.fr}
                      onChange={(e) => setNewTemplate({ ...newTemplate, fr: e.target.value })}
                      rows={4}
                      placeholder="Enter French message template..."
                      className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    />
                  </div>
                </div>

                {/* Placeholders Help */}
                <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <p className="text-sm font-semibold text-blue-800 mb-2">Available Placeholders:</p>
                  <div className="flex flex-wrap gap-2">
                    {["{customer_name}", "{appointment_date}", "{appointment_time}", "{branch_name}", "{service_name}", "{phone_number}", "{next_appointment_date}"].map((ph) => (
                      <code key={ph} className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">
                        {ph}
                      </code>
                    ))}
                  </div>
                </div>
              </div>

              <div className="p-6 border-t border-slate-200 flex justify-end space-x-3">
                <button
                  onClick={() => setShowCreateTemplateModal(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateTemplate}
                  disabled={savingTemplate === "new" || !newTemplate.id || !newTemplate.name}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 flex items-center space-x-2"
                >
                  <PlusIcon className="w-5 h-5" />
                  <span>{savingTemplate === "new" ? "Creating..." : "Create Template"}</span>
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default SmartMessaging;
