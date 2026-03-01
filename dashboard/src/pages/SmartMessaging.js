import React, { useState, useEffect } from "react";
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
  UserIcon,
  Squares2X2Icon,
  InboxIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  ArrowPathRoundedSquareIcon,
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

  // Fetch real data from API
  useEffect(() => {
    fetchSmartMessagingData();
    fetchSmartMessagingSettings();
    fetchPendingMessages();
    fetchServiceMappings();
    fetchTemplateSchedules();
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

  const fetchTemplateSchedules = async () => {
    try {
      const response = await fetch("/api/smart-messaging/template-schedules");
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
      const response = await fetch(`/api/smart-messaging/template-schedules/${templateId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: !!schedule.enabled,
          sendTime: schedule.sendTime || "15:00",
          timezone: schedule.timezone || "Asia/Beirut",
        }),
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
        const response = await fetch(`/api/smart-messaging/preview-queue/${message.message_id}`);
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
      const response = await fetch(`/api/smart-messaging/preview-queue/${viewingMessage.message_id}/edit`, {
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
        const response = await fetch(`/api/smart-messaging/preview-queue/${message.message_id}`);
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
      const response = await fetch(`/api/smart-messaging/preview-queue/${editingScheduledMessage.message_id}/edit`, {
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
      const response = await fetch(`/api/smart-messaging/preview-queue/${messageId}/reject`, {
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
      const response = await fetch(`/api/smart-messaging/templates/${editingTemplate.id}`, {
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
      const response = await fetch(`/api/smart-messaging/templates/${newTemplate.id}`, {
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
      const response = await fetch(`/api/smart-messaging/templates/${templateId}`, {
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
    try {
      setLoading(true);

      const fetchJsonSafely = async (url) => {
        try {
          const response = await fetch(url);
          return await response.json();
        } catch (error) {
          console.error(`Error fetching ${url}:`, error);
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
      setLoading(false);
    }
  };

  // Collect scheduled messages from appointments API, then refresh counts
  const handleCollectAndRefresh = async () => {
    try {
      setCollectingCounts(true);
      const baseURL =
        window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
          ? "http://localhost:8003"
          : window.location.origin;
      const response = await fetch(`${baseURL}/api/smart-messaging/collect-scheduled`, {
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

      const response = await fetch(`/api/smart-messaging/customers-by-category?category=${encodeURIComponent(category)}`);
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
      case "post_session_feedback":
        // Show messages scheduled for today only
        if (!sendDateStr) return true;
        return sendDateStr === todayStr;
      case "missed_yesterday":
        // Show yesterday's missed appointments
        return appointmentDate === yesterdayStr || sendDateStr === yesterdayStr;
      case "twenty_day_followup":
        // Show 20-day followups scheduled within current month
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
    post_session_feedback: Math.max(0, Number(messageCounts.post_session_feedback) || 0),
    twenty_day_followup: Math.max(0, Number(messageCounts.twenty_day_followup) || 0),
    missed_yesterday: Math.max(0, Number(messageCounts.missed_yesterday) || 0),
  };

  const getMessageTypeInfo = (type) => {
    const types = {
      reminder_24h: {
        name: "24h Reminder",
        color: "bg-blue-100 text-blue-700",
        icon: ClockIcon,
      },
      post_session_feedback: {
        name: "Feedback",
        color: "bg-green-100 text-green-700",
        icon: CheckCircleIcon,
      },
      twenty_day_followup: {
        name: "20-Day",
        color: "bg-indigo-100 text-indigo-700",
        icon: SparklesIcon,
      },
      missed_yesterday: {
        name: "Missed Yesterday",
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
      post_session_feedback: CheckCircleIcon,
      twenty_day_followup: SparklesIcon,
      missed_yesterday: ExclamationTriangleIcon,
    };
    // Return default icon for custom templates
    return icons[templateId] || EnvelopeIcon;
  };

  const getTemplateColor = (templateId) => {
    const colors = {
      reminder_24h: "from-blue-500 to-cyan-500",
      post_session_feedback: "from-green-500 to-emerald-500",
      twenty_day_followup: "from-indigo-500 to-purple-500",
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
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
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

                {/* 24h Reminder */}
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
                  <div className="font-bold text-sm">24h Reminder</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.reminder_24h}
                  </div>
                </button>

                {/* Post Session Feedback */}
                <button
                  onClick={() => handleCategorySelect("post_session_feedback")}
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

                {/* 20-Day Follow-up */}
                <button
                  onClick={() => handleCategorySelect("twenty_day_followup")}
                  className={`p-3 rounded-lg text-center transition-all transform hover:scale-105 ${
                    selectedMessageType === "twenty_day_followup"
                      ? "ring-2 ring-offset-2 ring-indigo-500 shadow-lg"
                      : "hover:shadow"
                  } ${
                    selectedMessageType === "twenty_day_followup"
                      ? "bg-gradient-to-br from-indigo-500 to-indigo-600 text-white"
                      : "bg-indigo-100 text-indigo-700 border border-indigo-300"
                  }`}
                >
                  <div className="font-bold text-sm">20-Day</div>
                  <div className="text-xs font-semibold mt-1">
                    {messageTypesCounts.twenty_day_followup}
                  </div>
                </button>

                {/* Missed Yesterday */}
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
                  <div className="font-bold text-sm">Missed Yesterday</div>
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
              {Object.entries(messageTemplates)
                .filter(([templateId]) => templateId !== "missed_paused_appointment")
                .map(([templateId, templateData]) => {
                  const Icon = getTemplateIcon(templateId);
                  const color = getTemplateColor(templateId);
                  const scheduleConfig = templateSchedules[templateId] || {
                    enabled: true,
                    sendTime: "15:00",
                    timezone: "Asia/Beirut",
                  };
                  const isDailyTemplate = [
                    "reminder_24h",
                    "post_session_feedback",
                    "missed_yesterday",
                    "twenty_day_followup",
                  ].includes(templateId);
                  const isActive = isDailyTemplate ? scheduleConfig.enabled !== false : true;
                  // Check if this is a custom template (not one of the default ones)
                  const defaultTemplates = [
                    "reminder_24h",
                    "post_session_feedback",
                    "twenty_day_followup",
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
                        <div className="flex-1">
                          <div className="flex items-center space-x-2">
                            <h3 className="font-bold text-slate-800">
                              {templateData.name}
                            </h3>
                            {isCustomTemplate && (
                              <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded">Custom</span>
                            )}
                          </div>
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
                                {isActive ? "✅ Daily Job Enabled" : "⏸️ Daily Job Disabled"}
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
