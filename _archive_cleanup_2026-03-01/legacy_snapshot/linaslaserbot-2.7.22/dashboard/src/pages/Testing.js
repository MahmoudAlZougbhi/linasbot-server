import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDropzone } from "react-dropzone";
import {
  MicrophoneIcon,
  PhotoIcon,
  ChatBubbleLeftIcon,
  PlayIcon,
  StopIcon,
  DocumentArrowUpIcon,
  SparklesIcon,
  LanguageIcon,
  ClockIcon,
  BeakerIcon,
  CodeBracketIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

const Testing = () => {
  const {
    testTextMessage,
    testVoiceTranscription,
    testImageAnalysis,
    testImageWithUrl,
    testVoiceWithText,
    loading,
    testMessageWithProvider,
    testWebhookSimulation,
  } = useApi();

  // Main tabs: Message Testing vs API Testing
  const [mainTab, setMainTab] = useState("message");

  // Message testing sub-tabs
  const [messageTab, setMessageTab] = useState("text");
  const [textInput, setTextInput] = useState("");
  const [selectedLanguage, setSelectedLanguage] = useState("auto");
  const [testResults, setTestResults] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [userPhone, setUserPhone] = useState("");
  const [userType, setUserType] = useState("customer");
  const [imageUrl, setImageUrl] = useState(
    "https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=400"
  );
  const [imageCaption, setImageCaption] = useState("هذا تاتو أريد إزالته");
  const [voiceText, setVoiceText] = useState(
    "مرحبا، أريد أعرف أسعار إزالة الشعر بالليزر للوجه"
  );

  // Hardcoded provider - MontyMobile (default)
  const selectedProvider = "montymobile";

  const mainTabs = [
    {
      id: "message",
      name: "Message Testing",
      icon: BeakerIcon,
      color: "from-blue-500 to-cyan-500",
    },
    {
      id: "api",
      name: "API Testing",
      icon: CodeBracketIcon,
      color: "from-purple-500 to-pink-500",
    },
  ];

  const messageTabs = [
    {
      id: "text",
      name: "Text Testing",
      icon: ChatBubbleLeftIcon,
      color: "from-blue-500 to-cyan-500",
    },
    {
      id: "voice",
      name: "Voice Testing",
      icon: MicrophoneIcon,
      color: "from-purple-500 to-pink-500",
    },
    {
      id: "image",
      name: "Image Testing",
      icon: PhotoIcon,
      color: "from-green-500 to-emerald-500",
    },
  ];

  const languages = [
    { code: "auto", name: "Auto Detect", flag: "🌐" },
    { code: "ar", name: "Arabic", flag: "🇸🇦" },
    { code: "en", name: "English", flag: "🇺🇸" },
    { code: "fr", name: "French", flag: "🇫🇷" },
    { code: "franco", name: "Franco-Arabic", flag: "🔤" },
  ];

  const sampleTexts = {
    ar: "مرحبا، أريد معلومات عن إزالة الشعر بالليزر",
    en: "Hello, I need information about laser hair removal",
    fr: "Bonjour, j'ai besoin d'informations sur l'épilation au laser",
    franco: "Marhaba, bade ma3loumat 3an laser hair removal",
  };

  // Handle text testing
  const handleTextTest = async () => {
    if (!textInput.trim()) {
      toast.error("Please enter a message to test");
      return;
    }

    try {
      const startTime = Date.now();
      const result = await testMessageWithProvider(
        textInput,
        selectedProvider,
        userPhone
      );
      const responseTime = Date.now() - startTime;

      const testResult = {
        id: Date.now(),
        type: "text",
        input: textInput,
        language: selectedLanguage,
        output:
          result.bot_response || result.response || "Test response received",
        responseTime: result.response_time_ms || responseTime,
        timestamp: new Date().toLocaleTimeString(),
        success: result.success !== false,
        mode: result.mode,
        userType: userType,
        userPhone: userPhone,
        provider: selectedProvider,
      };

      setTestResults((prev) => [testResult, ...prev]);

      // Don't clear input if in training mode
      if (result.mode !== "training" && result.mode !== "training_activated") {
        setTextInput("");
      }
    } catch (error) {
      const testResult = {
        id: Date.now(),
        type: "text",
        input: textInput,
        language: selectedLanguage,
        output: error.message,
        responseTime: 0,
        timestamp: new Date().toLocaleTimeString(),
        success: false,
        provider: selectedProvider,
      };
      setTestResults((prev) => [testResult, ...prev]);
    }
  };

  // Voice file dropzone
  const onVoiceDrop = useCallback(
    async (acceptedFiles) => {
      const file = acceptedFiles[0];
      if (!file) return;

      try {
        const startTime = Date.now();
        const result = await testVoiceTranscription(
          file,
          selectedProvider,
          userPhone
        );
        const responseTime = Date.now() - startTime;

        const testResult = {
          id: Date.now(),
          type: "voice",
          input: file.name,
          output:
            result.bot_response ||
            result.transcription ||
            "Voice message processed successfully",
          responseTime: result.response_time_ms || responseTime,
          timestamp: new Date().toLocaleTimeString(),
          success: result.success !== false,
          metadata: {
            fileSize: file.size,
            duration: result.duration || "Unknown",
            detectedLanguage: result.language || "Unknown",
          },
          provider: result.provider_info?.provider || "montymobile",
        };

        setTestResults((prev) => [testResult, ...prev]);
      } catch (error) {
        const testResult = {
          id: Date.now(),
          type: "voice",
          input: file.name,
          output: error.message,
          responseTime: 0,
          timestamp: new Date().toLocaleTimeString(),
          success: false,
        };
        setTestResults((prev) => [testResult, ...prev]);
      }
    },
    [testVoiceTranscription]
  );

  // Image file dropzone
  const onImageDrop = useCallback(
    async (acceptedFiles) => {
      const file = acceptedFiles[0];
      if (!file) return;

      try {
        const startTime = Date.now();
        const result = await testImageAnalysis(file);
        const responseTime = Date.now() - startTime;

        const testResult = {
          id: Date.now(),
          type: "image",
          input: file.name,
          output:
            result.bot_response ||
            result.analysis ||
            "Image analyzed successfully",
          responseTime,
          timestamp: new Date().toLocaleTimeString(),
          success: true,
          metadata: {
            fileSize: file.size,
            dimensions: result.dimensions || "Unknown",
            detectedObjects: result.objects || [],
          },
        };

        setTestResults((prev) => [testResult, ...prev]);
      } catch (error) {
        const testResult = {
          id: Date.now(),
          type: "image",
          input: file.name,
          output: error.message,
          responseTime: 0,
          timestamp: new Date().toLocaleTimeString(),
          success: false,
        };
        setTestResults((prev) => [testResult, ...prev]);
      }
    },
    [testImageAnalysis]
  );

  const {
    getRootProps: getVoiceRootProps,
    getInputProps: getVoiceInputProps,
    isDragActive: isVoiceDragActive,
  } = useDropzone({
    onDrop: onVoiceDrop,
    accept: {
      "audio/*": [".mp3", ".wav", ".ogg", ".m4a"],
    },
    maxFiles: 1,
  });

  const {
    getRootProps: getImageRootProps,
    getInputProps: getImageInputProps,
    isDragActive: isImageDragActive,
  } = useDropzone({
    onDrop: onImageDrop,
    accept: {
      "image/*": [".png", ".jpg", ".jpeg", ".gif", ".webp"],
    },
    maxFiles: 1,
  });

  const clearResults = () => {
    setTestResults([]);
    toast.success("Test results cleared");
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center"
      >
        <h1 className="text-4xl font-bold gradient-text font-display mb-4">
          AI Testing Laboratory
        </h1>
        <p className="text-xl text-slate-600 max-w-2xl mx-auto">
          Test your bot's capabilities with text, voice, and image inputs.
          Perfect your AI before going live.
        </p>
      </motion.div>

      {/* Main Tabs: Message Testing vs API Testing */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="flex justify-center"
      >
        <div className="glass rounded-2xl p-2 inline-flex space-x-2">
          {mainTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setMainTab(tab.id)}
              className={`relative flex items-center space-x-2 px-8 py-4 rounded-xl font-medium transition-all duration-200 ${
                mainTab === tab.id
                  ? "text-white shadow-lg"
                  : "text-slate-600 hover:text-slate-800 hover:bg-white/50"
              }`}
            >
              {mainTab === tab.id && (
                <motion.div
                  layoutId="activeMainTab"
                  className={`absolute inset-0 bg-gradient-to-r ${tab.color} rounded-xl`}
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
              <tab.icon className="w-6 h-6 relative z-10" />
              <span className="relative z-10 text-lg">{tab.name}</span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Content based on main tab */}
      <AnimatePresence mode="wait">
        {mainTab === "message" && (
          <motion.div
            key="message-testing"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.4 }}
            className="space-y-6"
          >
            {/* Message Type Tabs */}
            <div className="flex justify-center">
              <div className="glass rounded-2xl p-2 inline-flex space-x-2">
                {messageTabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setMessageTab(tab.id)}
                    className={`relative flex items-center space-x-2 px-6 py-3 rounded-xl font-medium transition-all duration-200 ${
                      messageTab === tab.id
                        ? "text-white shadow-lg"
                        : "text-slate-600 hover:text-slate-800 hover:bg-white/50"
                    }`}
                  >
                    {messageTab === tab.id && (
                      <motion.div
                        layoutId="activeMessageTab"
                        className={`absolute inset-0 bg-gradient-to-r ${tab.color} rounded-xl`}
                        transition={{
                          type: "spring",
                          bounce: 0.2,
                          duration: 0.6,
                        }}
                      />
                    )}
                    <tab.icon className="w-5 h-5 relative z-10" />
                    <span className="relative z-10">{tab.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Provider Info Badge */}
            <div className="flex justify-center">
              <div className="glass rounded-xl px-4 py-2 inline-flex items-center space-x-2 bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200">
                <span className="text-2xl">🟣</span>
                <span className="text-sm font-medium text-purple-700">
                  Provider: MontyMobile
                </span>
              </div>
            </div>

            {/* Testing Interface */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Input Section */}
              <div className="space-y-6">
                <div className="card">
                  <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
                    <SparklesIcon className="w-6 h-6 mr-2 text-primary-600" />
                    Test Input
                  </h2>

                  <AnimatePresence mode="wait">
                    {messageTab === "text" && (
                      <motion.div
                        key="text"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.3 }}
                        className="space-y-4"
                      >
                        {/* User Simulation */}
                        <div className="glass rounded-xl p-4 bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 mb-4">
                          <h3 className="font-medium text-purple-800 mb-3">
                            🎭 User Simulation
                          </h3>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="block text-xs font-medium text-purple-700 mb-1">
                                User Type
                              </label>
                              <select
                                value={userType}
                                onChange={(e) => {
                                  setUserType(e.target.value);
                                  if (e.target.value === "admin") {
                                    setUserPhone("9613956607");
                                  } else if (e.target.value === "new") {
                                    setUserPhone("9611234567");
                                  } else {
                                    setUserPhone("9619876543");
                                  }
                                }}
                                className="input-field w-full text-sm"
                              >
                                <option value="customer">
                                  👤 Existing Customer
                                </option>
                                <option value="new">🆕 New User</option>
                                <option value="admin">
                                  👑 Admin (Training Mode)
                                </option>
                              </select>
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-purple-700 mb-1">
                                Phone Number
                              </label>
                              <input
                                type="text"
                                value={userPhone}
                                onChange={(e) => setUserPhone(e.target.value)}
                                placeholder="961XXXXXXXX"
                                className="input-field w-full text-sm"
                              />
                            </div>
                          </div>
                          {userType === "admin" && (
                            <div className="mt-2 text-xs text-purple-600">
                              💡 Try typing "training" to activate training
                              mode!
                            </div>
                          )}
                          {userType === "new" && (
                            <div className="mt-2 text-xs text-purple-600">
                              💡 Bot will ask for gender on first interaction
                            </div>
                          )}
                        </div>

                        {/* Language Selection */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            <LanguageIcon className="w-4 h-4 inline mr-1" />
                            Language
                          </label>
                          <select
                            value={selectedLanguage}
                            onChange={(e) =>
                              setSelectedLanguage(e.target.value)
                            }
                            className="input-field w-full"
                          >
                            {languages.map((lang) => (
                              <option key={lang.code} value={lang.code}>
                                {lang.flag} {lang.name}
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Text Input */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            Message
                          </label>
                          <textarea
                            value={textInput}
                            onChange={(e) => setTextInput(e.target.value)}
                            placeholder="Enter your message here..."
                            className="input-field w-full h-32 resize-none"
                          />
                        </div>

                        {/* Sample Texts */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            Quick Samples
                          </label>
                          <div className="grid grid-cols-2 gap-2">
                            {Object.entries(sampleTexts).map(([lang, text]) => (
                              <button
                                key={lang}
                                onClick={() => setTextInput(text)}
                                className="btn-ghost text-left text-sm p-3 h-auto"
                              >
                                <div className="font-medium">
                                  {languages.find((l) => l.code === lang)?.flag}{" "}
                                  {lang.toUpperCase()}
                                </div>
                                <div className="text-xs text-slate-500 mt-1 truncate">
                                  {text}
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Test Buttons */}
                        <div className="grid grid-cols-1 gap-3">
                          <button
                            onClick={handleTextTest}
                            disabled={loading || !textInput.trim()}
                            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Processing...
                              </div>
                            ) : (
                              <>
                                <PlayIcon className="w-4 h-4 mr-2" />
                                Test Message (Direct)
                              </>
                            )}
                          </button>

                          {/* Firebase Test Button */}
                          <button
                            onClick={async () => {
                              try {
                                const startTime = Date.now();
                                const response = await fetch(
                                  "/api/test-firebase",
                                  {
                                    method: "POST",
                                    headers: {
                                      "Content-Type": "application/json",
                                    },
                                  }
                                );
                                const result = await response.json();
                                const responseTime = Date.now() - startTime;

                                const testResult = {
                                  id: Date.now(),
                                  type: "firebase",
                                  input: "Firebase Connection Test",
                                  output: result.success
                                    ? `✅ Firebase test successful! ${result.results.conversations_saved} conversations saved, Firestore connected: ${result.results.firestore_connected}, Metrics updated: ${result.results.metrics_updated}`
                                    : `❌ Firebase test failed: ${result.error}`,
                                  responseTime,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: result.success,
                                  metadata: result.results || {},
                                };

                                setTestResults((prev) => [testResult, ...prev]);

                                if (result.success) {
                                  toast.success(
                                    "Firebase test completed successfully!"
                                  );
                                } else {
                                  toast.error(
                                    `Firebase test failed: ${result.error}`
                                  );
                                }
                              } catch (error) {
                                const testResult = {
                                  id: Date.now(),
                                  type: "firebase",
                                  input: "Firebase Connection Test",
                                  output: `❌ Network error: ${error.message}`,
                                  responseTime: 0,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: false,
                                };
                                setTestResults((prev) => [testResult, ...prev]);
                                toast.error(
                                  `Firebase test error: ${error.message}`
                                );
                              }
                            }}
                            disabled={loading}
                            className="btn-secondary w-full disabled:opacity-50 disabled:cursor-not-allowed bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Testing...
                              </div>
                            ) : (
                              <>🔥 Test Firebase Connection</>
                            )}
                          </button>

                          <button
                            onClick={async () => {
                              if (!textInput.trim()) {
                                toast.error("Please enter a message to test");
                                return;
                              }

                              try {
                                const startTime = Date.now();
                                const result = await testWebhookSimulation(
                                  textInput,
                                  selectedProvider,
                                  userPhone
                                );
                                const responseTime = Date.now() - startTime;

                                const testResult = {
                                  id: Date.now(),
                                  type: "webhook",
                                  input: textInput,
                                  language: selectedLanguage,
                                  output:
                                    result.bot_response ||
                                    result.response ||
                                    "Webhook test response received",
                                  responseTime:
                                    result.response_time_ms || responseTime,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: result.success !== false,
                                  mode: result.mode,
                                  userType: userType,
                                  userPhone: userPhone,
                                  provider: selectedProvider,
                                  webhookPayload: result.webhook_payload,
                                };

                                setTestResults((prev) => [testResult, ...prev]);

                                // Don't clear input if in training mode
                                if (
                                  result.mode !== "training" &&
                                  result.mode !== "training_activated"
                                ) {
                                  setTextInput("");
                                }
                              } catch (error) {
                                const testResult = {
                                  id: Date.now(),
                                  type: "webhook",
                                  input: textInput,
                                  language: selectedLanguage,
                                  output: error.message,
                                  responseTime: 0,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: false,
                                  provider: selectedProvider,
                                };
                                setTestResults((prev) => [testResult, ...prev]);
                              }
                            }}
                            disabled={loading || !textInput.trim()}
                            className="btn-secondary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Processing...
                              </div>
                            ) : (
                              <>
                                <DocumentArrowUpIcon className="w-4 h-4 mr-2" />
                                Test Webhook Simulation
                              </>
                            )}
                          </button>
                        </div>

                        {/* Test Mode Info */}
                        <div className="glass rounded-xl p-3 bg-blue-50 border border-blue-200">
                          <div className="text-xs text-blue-700">
                            <div className="font-medium mb-1">
                              🔍 Testing Modes:
                            </div>
                            <div className="space-y-1">
                              <div>
                                <strong>Direct:</strong> Tests bot logic
                                directly (bypasses webhook)
                              </div>
                              <div>
                                <strong>Webhook:</strong> Simulates full webhook
                                flow from MontyMobile
                              </div>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}

                    {messageTab === "voice" && (
                      <motion.div
                        key="voice"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.3 }}
                        className="space-y-4"
                      >
                        {/* Voice Text Testing */}
                        <div className="space-y-4">
                          <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">
                              Voice Message Text (Simulated Transcription)
                            </label>
                            <textarea
                              value={voiceText}
                              onChange={(e) => setVoiceText(e.target.value)}
                              placeholder="Enter what the voice message would say after transcription..."
                              className="input-field w-full h-32 resize-none"
                            />
                          </div>

                          <button
                            onClick={async () => {
                              if (!voiceText.trim()) {
                                toast.error("Please enter voice text to test");
                                return;
                              }

                              try {
                                const startTime = Date.now();
                                const result = await testVoiceWithText(
                                  voiceText,
                                  selectedProvider,
                                  userPhone
                                );
                                const responseTime = Date.now() - startTime;

                                const testResult = {
                                  id: Date.now(),
                                  type: "voice-text",
                                  input: `[Voice: ${voiceText}]`,
                                  output:
                                    result.bot_response ||
                                    "Voice message processed successfully",
                                  responseTime:
                                    result.response_time_ms || responseTime,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: result.success !== false,
                                  provider: selectedProvider,
                                };

                                setTestResults((prev) => [testResult, ...prev]);
                              } catch (error) {
                                const testResult = {
                                  id: Date.now(),
                                  type: "voice-text",
                                  input: `[Voice: ${voiceText}]`,
                                  output: error.message,
                                  responseTime: 0,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: false,
                                  provider: selectedProvider,
                                };
                                setTestResults((prev) => [testResult, ...prev]);
                              }
                            }}
                            disabled={loading || !voiceText.trim()}
                            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Processing...
                              </div>
                            ) : (
                              <>
                                <MicrophoneIcon className="w-4 h-4 mr-2" />
                                Test Voice Message
                              </>
                            )}
                          </button>
                        </div>

                        {/* Voice Upload */}
                        <div
                          {...getVoiceRootProps()}
                          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${
                            isVoiceDragActive
                              ? "border-primary-400 bg-primary-50"
                              : "border-slate-300 hover:border-primary-400 hover:bg-primary-50"
                          }`}
                        >
                          <input {...getVoiceInputProps()} />
                          <MicrophoneIcon className="w-12 h-12 text-slate-400 mx-auto mb-4" />
                          <p className="text-lg font-medium text-slate-700 mb-2">
                            {isVoiceDragActive
                              ? "Drop your audio file here"
                              : "Upload Voice File (Advanced)"}
                          </p>
                          <p className="text-sm text-slate-500">
                            Drag & drop or click to select • MP3, WAV, OGG, M4A
                          </p>
                        </div>

                        {/* Recording Note */}
                        <div className="glass rounded-xl p-4 bg-amber-50 border border-amber-200">
                          <div className="flex items-start space-x-3">
                            <MicrophoneIcon className="w-5 h-5 text-amber-600 mt-0.5" />
                            <div>
                              <h4 className="font-medium text-amber-800">
                                Voice Testing Options
                              </h4>
                              <p className="text-sm text-amber-700 mt-1">
                                <strong>Text Simulation:</strong> Test bot
                                response to voice messages by entering the
                                transcribed text.
                                <br />
                                <strong>File Upload:</strong> Upload actual
                                audio files for transcription testing
                                (advanced).
                              </p>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}

                    {messageTab === "image" && (
                      <motion.div
                        key="image"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.3 }}
                        className="space-y-4"
                      >
                        {/* Image URL Testing */}
                        <div className="space-y-4">
                          <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">
                              Image URL
                            </label>
                            <input
                              type="url"
                              value={imageUrl}
                              onChange={(e) => setImageUrl(e.target.value)}
                              placeholder="https://example.com/image.jpg"
                              className="input-field w-full"
                            />
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">
                              Caption (Optional)
                            </label>
                            <input
                              type="text"
                              value={imageCaption}
                              onChange={(e) => setImageCaption(e.target.value)}
                              placeholder="Image caption..."
                              className="input-field w-full"
                            />
                          </div>

                          <button
                            onClick={async () => {
                              if (!imageUrl.trim()) {
                                toast.error(
                                  "Please enter an image URL to test"
                                );
                                return;
                              }

                              try {
                                const startTime = Date.now();
                                const result = await testImageWithUrl(
                                  imageUrl,
                                  imageCaption,
                                  selectedProvider,
                                  userPhone
                                );
                                const responseTime = Date.now() - startTime;

                                const testResult = {
                                  id: Date.now(),
                                  type: "image-url",
                                  input: `[Image: ${imageUrl}] ${imageCaption}`,
                                  output:
                                    result.bot_response ||
                                    "Image analyzed successfully",
                                  responseTime:
                                    result.response_time_ms || responseTime,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: result.success !== false,
                                  provider: selectedProvider,
                                };

                                setTestResults((prev) => [testResult, ...prev]);
                              } catch (error) {
                                const testResult = {
                                  id: Date.now(),
                                  type: "image-url",
                                  input: `[Image: ${imageUrl}] ${imageCaption}`,
                                  output: error.message,
                                  responseTime: 0,
                                  timestamp: new Date().toLocaleTimeString(),
                                  success: false,
                                  provider: selectedProvider,
                                };
                                setTestResults((prev) => [testResult, ...prev]);
                              }
                            }}
                            disabled={loading || !imageUrl.trim()}
                            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Analyzing...
                              </div>
                            ) : (
                              <>
                                <PhotoIcon className="w-4 h-4 mr-2" />
                                Test Image Analysis
                              </>
                            )}
                          </button>
                        </div>

                        {/* Image Upload */}
                        <div
                          {...getImageRootProps()}
                          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${
                            isImageDragActive
                              ? "border-green-400 bg-green-50"
                              : "border-slate-300 hover:border-green-400 hover:bg-green-50"
                          }`}
                        >
                          <input {...getImageInputProps()} />
                          <PhotoIcon className="w-12 h-12 text-slate-400 mx-auto mb-4" />
                          <p className="text-lg font-medium text-slate-700 mb-2">
                            {isImageDragActive
                              ? "Drop your image here"
                              : "Upload Image File (Advanced)"}
                          </p>
                          <p className="text-sm text-slate-500">
                            Drag & drop or click to select • PNG, JPG, JPEG,
                            GIF, WebP
                          </p>
                        </div>

                        {/* Image Analysis Note */}
                        <div className="glass rounded-xl p-4 bg-blue-50 border border-blue-200">
                          <div className="flex items-start space-x-3">
                            <PhotoIcon className="w-5 h-5 text-blue-600 mt-0.5" />
                            <div>
                              <h4 className="font-medium text-blue-800">
                                Image Testing Options
                              </h4>
                              <p className="text-sm text-blue-700 mt-1">
                                <strong>URL Testing:</strong> Test bot response
                                to images by providing a URL (recommended).
                                <br />
                                <strong>File Upload:</strong> Upload actual
                                image files for analysis testing (advanced).
                              </p>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {/* Results Section */}
              <div className="space-y-6">
                <div className="card h-full">
                  <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-bold text-slate-800 font-display flex items-center">
                      <ClockIcon className="w-6 h-6 mr-2 text-secondary-600" />
                      Test Results
                    </h2>
                    {testResults.length > 0 && (
                      <button
                        onClick={clearResults}
                        className="text-sm text-slate-500 hover:text-slate-700 transition-colors"
                      >
                        Clear All
                      </button>
                    )}
                  </div>

                  <div className="space-y-4 max-h-96 overflow-y-auto scrollbar-hide">
                    <AnimatePresence>
                      {testResults.length === 0 ? (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="text-center py-12"
                        >
                          <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                            <SparklesIcon className="w-8 h-8 text-slate-400" />
                          </div>
                          <p className="text-slate-500">No test results yet</p>
                          <p className="text-sm text-slate-400 mt-1">
                            Run a test to see results here
                          </p>
                        </motion.div>
                      ) : (
                        testResults.map((result) => (
                          <motion.div
                            key={result.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -20 }}
                            transition={{ duration: 0.3 }}
                            className={`glass rounded-xl p-4 border-l-4 ${
                              result.success
                                ? "border-green-400"
                                : "border-red-400"
                            }`}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center space-x-2">
                                <span
                                  className={`px-2 py-1 text-xs font-medium rounded-full ${
                                    result.type === "text"
                                      ? "bg-blue-100 text-blue-700"
                                      : result.type === "voice"
                                      ? "bg-purple-100 text-purple-700"
                                      : result.type === "webhook"
                                      ? "bg-indigo-100 text-indigo-700"
                                      : result.type === "firebase"
                                      ? "bg-orange-100 text-orange-700"
                                      : "bg-green-100 text-green-700"
                                  }`}
                                >
                                  {result.type === "firebase"
                                    ? "🔥 firebase"
                                    : result.type}
                                </span>
                                <span className="text-xs text-slate-500">
                                  {result.timestamp}
                                </span>
                              </div>
                              <span className="text-xs text-slate-500">
                                {result.responseTime}ms
                              </span>
                            </div>

                            <div className="space-y-2">
                              <div>
                                <p className="text-xs font-medium text-slate-600 mb-1">
                                  Input:
                                </p>
                                <p className="text-sm text-slate-800 bg-slate-50 rounded p-2">
                                  {result.input}
                                </p>
                              </div>

                              <div>
                                <p className="text-xs font-medium text-slate-600 mb-1">
                                  Output:
                                </p>
                                <p
                                  className={`text-sm rounded p-2 ${
                                    result.success
                                      ? "text-slate-800 bg-green-50"
                                      : "text-red-700 bg-red-50"
                                  }`}
                                >
                                  {result.output}
                                </p>
                              </div>

                              {result.metadata && (
                                <div className="text-xs text-slate-500 space-y-1">
                                  {result.metadata.fileSize && (
                                    <p>
                                      Size:{" "}
                                      {(
                                        result.metadata.fileSize / 1024
                                      ).toFixed(1)}
                                      KB
                                    </p>
                                  )}
                                  {result.metadata.detectedLanguage && (
                                    <p>
                                      Language:{" "}
                                      {result.metadata.detectedLanguage}
                                    </p>
                                  )}
                                </div>
                              )}
                            </div>
                          </motion.div>
                        ))
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {mainTab === "api" && (
          <motion.div
            key="api-testing"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.4 }}
            className="space-y-6"
          >
            <APITestingPanel />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// API Testing Panel Component
const APITestingPanel = () => {
  const [apiResults, setApiResults] = useState([]);
  const [testingAll, setTestingAll] = useState(false);
  const [testingEndpoint, setTestingEndpoint] = useState(null);

  // Use relative URL to go through Apache proxy
  const API_BASE_URL = process.env.REACT_APP_API_URL || "";

  // Define all API endpoints organized by category
  const apiEndpoints = {
    "System & Health": [
      {
        id: "health",
        name: "Health Check",
        method: "GET",
        endpoint: "/agent/health",
        params: {},
        requiresAuth: false,
      },
      {
        id: "status",
        name: "API Status",
        method: "GET",
        endpoint: "/agent/status",
        params: {},
        requiresAuth: true,
      },
      {
        id: "tenant-details",
        name: "Clinic Details",
        method: "GET",
        endpoint: "/agent/tenant/details",
        params: {},
        requiresAuth: true,
      },
    ],
    "Clinic Data": [
      {
        id: "branches",
        name: "List Branches",
        method: "GET",
        endpoint: "/agent/branches",
        params: {},
        requiresAuth: true,
      },
      {
        id: "services",
        name: "List Services",
        method: "GET",
        endpoint: "/agent/services",
        params: {},
        requiresAuth: true,
      },
      {
        id: "machines",
        name: "List Machines",
        method: "GET",
        endpoint: "/agent/machines",
        params: {},
        requiresAuth: true,
      },
      {
        id: "clinic-hours",
        name: "Clinic Hours",
        method: "GET",
        endpoint: "/agent/clinic/hours",
        params: {},
        requiresAuth: true,
      },
    ],
    "Customer Management": [
      {
        id: "customer-gender",
        name: "Check Customer Gender",
        method: "GET",
        endpoint: "/agent/customers/gender",
        params: { phone: "3956607" },
        requiresAuth: true,
      },
      {
        id: "customer-by-phone",
        name: "Get Customer by Phone",
        method: "GET",
        endpoint: "/agent/customers/by-phone",
        params: { phone: "3956607" },
        requiresAuth: true,
      },
      {
        id: "create-customer",
        name: "Create Customer",
        method: "POST",
        endpoint: "/agent/customers/create",
        body: {
          name: "Test User",
          phone: "9611234567",
          gender: "Male",
          branch_id: 1,
        },
        requiresAuth: true,
      },
      {
        id: "customer-balance",
        name: "Get Customer Balance",
        method: "GET",
        endpoint: "/agent/customers/balance",
        params: { customer_id: 4 },
        requiresAuth: true,
      },
      {
        id: "customer-sessions",
        name: "Get Customer Sessions",
        method: "GET",
        endpoint: "/agent/customers/sessions",
        params: { customer_id: 4 },
        requiresAuth: true,
      },
      {
        id: "customer-appointments",
        name: "List Customer Appointments",
        method: "GET",
        endpoint: "/agent/appointments/customer",
        params: { phone: 71123456 },
        requiresAuth: true,
      },
      {
        id: "add-customer-note",
        name: "Add Customer Note",
        method: "POST",
        endpoint: "/agent/customers/notes/add",
        body: {
          phone: "3956607",
          note: "Test note added via API",
        },
        requiresAuth: true,
      },
    ],
    "Appointment Management": [
      {
        id: "next-appointment",
        name: "Check Next Appointment",
        method: "GET",
        endpoint: "/agent/appointments/next",
        params: { phone: "3956607" },
        requiresAuth: true,
      },
      {
        id: "sessions-count",
        name: "Get Sessions Count",
        method: "GET",
        endpoint: "/agent/appointments/sessions/count",
        params: { phone: "3956607" },
        requiresAuth: true,
      },
      {
        id: "appointment-payment",
        name: "Check Payment Status",
        method: "GET",
        endpoint: "/agent/appointments/payment",
        params: { phone: "3956607" },
        requiresAuth: true,
      },
      {
        id: "appointment-pricing",
        name: "Get Pricing Details",
        method: "GET",
        endpoint: "/agent/appointments/pricing",
        params: { service_id: 1, machine_id: 1 },
        requiresAuth: true,
      },
      {
        id: "missed-appointments",
        name: "Get Missed Appointments",
        method: "GET",
        endpoint: "/agent/appointments/missed",
        params: {},
        requiresAuth: true,
      },
      {
        id: "appointment-reminders",
        name: "Send Appointment Reminders",
        method: "GET",
        endpoint: "/agent/appointments/reminders",
        params: { phone: "3956607" },
        requiresAuth: true,
      },
      {
        id: "create-appointment",
        name: "Create Appointment",
        method: "POST",
        endpoint: "/agent/appointments/create",
        body: {
          phone: "3956607",
          service_id: 1,
          machine_id: 1,
          branch_id: 1,
          date: "2025-12-01 14:00:00",
        },
        requiresAuth: true,
      },
      {
        id: "update-appointment",
        name: "Update Appointment",
        method: "POST",
        endpoint: "/agent/appointments/update/date",
        body: { appointment_id: 456, date: "2025-12-02 15:00:00" },
        requiresAuth: true,
      },
      {
        id: "cancel-appointment",
        name: "Cancel Appointment",
        method: "POST",
        endpoint: "/agent/appointments/cancel",
        body: {
          appointment_id: 21247,
          phone: "3956607",
          reason: "Customer request",
        },
        requiresAuth: true,
      },
      {
        id: "appointment-details",
        name: "Get Appointment Details",
        method: "GET",
        endpoint: "/agent/appointments/details",
        params: { appointment_id: 21247 },
        requiresAuth: true,
      },
      {
        id: "move-branch",
        name: "Move Client Branch",
        method: "POST",
        endpoint: "/agent/appointments/branch/move",
        body: {
          phone: "9613956607",
          from_branch_id: 1,
          to_branch_id: 2,
          response: "yes",
        },
        requiresAuth: true,
      },
    ],
    "Payment & Transactions": [
      {
        id: "mark-paid",
        name: "Mark Payment as Paid",
        method: "POST",
        endpoint: "/agent/transactions/mark-paid",
        body: { transaction_id: 999, payment_method: "cash", amount: 200 },
        requiresAuth: true,
      },
    ],
    "Q&A System": [
      {
        id: "qa-list",
        name: "Get All Q&A Entries",
        method: "GET",
        endpoint: "/agent/qa/list",
        params: { language: "ar" },
        requiresAuth: true,
      },
      {
        id: "qa-search",
        name: "Search Q&A Entries",
        method: "GET",
        endpoint: "/agent/qa/search",
        params: { query: "laser", language: "ar" },
        requiresAuth: true,
      },
      {
        id: "qa-categories",
        name: "Get Q&A Categories",
        method: "GET",
        endpoint: "/agent/qa/categories",
        params: {},
        requiresAuth: true,
      },
      {
        id: "qa-create",
        name: "Create Q&A Entry",
        method: "POST",
        endpoint: "/agent/qa/create",
        body: {
          question_ar: "سؤال تجريبي؟",
          answer_ar: "جواب تجريبي",
          category: "general",
        },
        requiresAuth: true,
      },
      {
        id: "qa-update",
        name: "Update Q&A Entry",
        method: "POST",
        endpoint: "/agent/qa/update",
        body: { qa_id: 101, answer_ar: "جواب محدث" },
        requiresAuth: true,
      },
      {
        id: "qa-delete",
        name: "Delete Q&A Entry",
        method: "POST",
        endpoint: "/agent/qa/delete",
        body: { qa_id: 101 },
        requiresAuth: true,
      },
      {
        id: "qa-track-usage",
        name: "Track Q&A Usage",
        method: "POST",
        endpoint: "/agent/qa/track-usage",
        body: { qa_id: 101, customer_phone: "9613956607", matched: true },
        requiresAuth: true,
      },
    ],
    "Content Management": [
      {
        id: "knowledge-base",
        name: "Get Knowledge Base",
        method: "GET",
        endpoint: "/agent/content/knowledge-base",
        params: {},
        requiresAuth: true,
      },
      {
        id: "update-knowledge-base",
        name: "Update Knowledge Base",
        method: "POST",
        endpoint: "/agent/content/knowledge-base/update",
        body: { content_ar: "محتوى محدث", content_en: "Updated content" },
        requiresAuth: true,
      },
      {
        id: "style-guide",
        name: "Get Style Guide",
        method: "GET",
        endpoint: "/agent/content/style-guide",
        params: {},
        requiresAuth: true,
      },
      {
        id: "price-list",
        name: "Get Price List",
        method: "GET",
        endpoint: "/agent/content/price-list",
        params: {},
        requiresAuth: true,
      },
    ],
    "Logs & Reports": [
      {
        id: "conversation-log",
        name: "Get Conversation Logs",
        method: "GET",
        endpoint: "/agent/logs/conversation",
        params: { phone: "9613956607", date: "2025-01-09" },
        requiresAuth: true,
      },
      {
        id: "save-conversation",
        name: "Save Conversation Log",
        method: "POST",
        endpoint: "/agent/logs/conversation",
        body: {
          customer_phone: "9613956607",
          message: "Hello",
          response: "Hi!",
          language: "en",
        },
        requiresAuth: true,
      },
      {
        id: "daily-report",
        name: "Get Daily Report",
        method: "GET",
        endpoint: "/agent/logs/daily-report",
        params: { date: "2025-01-09" },
        requiresAuth: true,
      },
      {
        id: "report-event",
        name: "Log Report Event",
        method: "POST",
        endpoint: "/agent/logs/report-event",
        body: { event_type: "test_event", user_id: "9613956607", details: {} },
        requiresAuth: true,
      },
    ],
  };

  const testEndpoint = async (endpoint) => {
    setTestingEndpoint(endpoint.id);
    const startTime = Date.now();

    try {
      let url = `${API_BASE_URL}${endpoint.endpoint}`;

      // Add query parameters for GET requests
      if (
        endpoint.method === "GET" &&
        endpoint.params &&
        Object.keys(endpoint.params).length > 0
      ) {
        const queryString = new URLSearchParams(endpoint.params).toString();
        url += `?${queryString}`;
      }

      const options = {
        method: endpoint.method,
        headers: {
          "Content-Type": "application/json",
        },
      };

      // Add auth token if required
      if (endpoint.requiresAuth) {
        const token = localStorage.getItem("api_token") || "YOUR_API_TOKEN";
        options.headers["Authorization"] = `Bearer ${token}`;
      }

      // Add body for POST requests
      if (endpoint.method === "POST" && endpoint.body) {
        options.body = JSON.stringify(endpoint.body);
      }

      const response = await fetch(url, options);
      const data = await response.json();
      const responseTime = Date.now() - startTime;

      const result = {
        id: Date.now(),
        endpoint: endpoint.name,
        method: endpoint.method,
        url: url,
        status: response.status,
        success: response.ok,
        data: data,
        responseTime: responseTime,
        timestamp: new Date().toLocaleTimeString(),
      };

      setApiResults((prev) => [result, ...prev]);

      if (response.ok) {
        toast.success(`�� ${endpoint.name} - Success`);
      } else {
        toast.error(`❌ ${endpoint.name} - ${response.status}`);
      }
    } catch (error) {
      const responseTime = Date.now() - startTime;
      const result = {
        id: Date.now(),
        endpoint: endpoint.name,
        method: endpoint.method,
        url: `${API_BASE_URL}${endpoint.endpoint}`,
        status: 0,
        success: false,
        data: { error: error.message },
        responseTime: responseTime,
        timestamp: new Date().toLocaleTimeString(),
      };

      setApiResults((prev) => [result, ...prev]);
      toast.error(`❌ ${endpoint.name} - ${error.message}`);
    } finally {
      setTestingEndpoint(null);
    }
  };

  const testAllEndpoints = async () => {
    setTestingAll(true);
    setApiResults([]);

    for (const category of Object.keys(apiEndpoints)) {
      for (const endpoint of apiEndpoints[category]) {
        await testEndpoint(endpoint);
        // Small delay between requests
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }

    setTestingAll(false);
    toast.success("All API tests completed!");
  };

  const clearApiResults = () => {
    setApiResults([]);
    toast.success("API results cleared");
  };

  return (
    <div className="space-y-6">
      {/* Header with Test All Button */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-800 font-display">
              Backend API Endpoints
            </h2>
            <p className="text-sm text-slate-600 mt-1">
              Test all backend endpoints individually or run all tests at once
            </p>
          </div>
          <button
            onClick={testAllEndpoints}
            disabled={testingAll}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testingAll ? (
              <div className="flex items-center">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Testing All...
              </div>
            ) : (
              <>
                <PlayIcon className="w-4 h-4 mr-2" />
                Test All Endpoints
              </>
            )}
          </button>
        </div>

        {/* API Token Input */}
        <div className="glass rounded-xl p-4 bg-amber-50 border border-amber-200">
          <label className="block text-sm font-medium text-amber-800 mb-2">
            🔑 API Token (Optional - stored in localStorage)
          </label>
          <input
            type="text"
            placeholder="Enter your API token..."
            defaultValue={localStorage.getItem("api_token") || ""}
            onChange={(e) => localStorage.setItem("api_token", e.target.value)}
            className="input-field w-full text-sm"
          />
          <p className="text-xs text-amber-600 mt-2">
            Token is required for authenticated endpoints. Get your token from
            the backend admin panel.
          </p>
        </div>
      </div>

      {/* API Endpoints by Category */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column - Endpoints */}
        <div className="space-y-6">
          {Object.entries(apiEndpoints).map(([category, endpoints]) => (
            <div key={category} className="card">
              <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center">
                <span className="w-2 h-2 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full mr-2"></span>
                {category}
                <span className="ml-2 text-xs font-normal text-slate-500">
                  ({endpoints.length})
                </span>
              </h3>
              <div className="space-y-2">
                {endpoints.map((endpoint) => (
                  <div
                    key={endpoint.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <span
                          className={`px-2 py-0.5 text-xs font-medium rounded ${
                            endpoint.method === "GET"
                              ? "bg-blue-100 text-blue-700"
                              : "bg-green-100 text-green-700"
                          }`}
                        >
                          {endpoint.method}
                        </span>
                        <span className="text-sm font-medium text-slate-800">
                          {endpoint.name}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1 font-mono">
                        {endpoint.endpoint}
                      </p>
                    </div>
                    <button
                      onClick={() => testEndpoint(endpoint)}
                      disabled={testingEndpoint === endpoint.id || testingAll}
                      className="btn-ghost px-3 py-1 text-sm disabled:opacity-50"
                    >
                      {testingEndpoint === endpoint.id ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-600"></div>
                      ) : (
                        <PlayIcon className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Right Column - Results */}
        <div className="space-y-6">
          <div className="card sticky top-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-800 flex items-center">
                <ClockIcon className="w-5 h-5 mr-2 text-secondary-600" />
                Test Results
              </h3>
              {apiResults.length > 0 && (
                <button
                  onClick={clearApiResults}
                  className="text-sm text-slate-500 hover:text-slate-700 transition-colors"
                >
                  Clear All
                </button>
              )}
            </div>

            <div className="space-y-3 max-h-[600px] overflow-y-auto scrollbar-hide">
              <AnimatePresence>
                {apiResults.length === 0 ? (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-center py-12"
                  >
                    <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                      <CodeBracketIcon className="w-8 h-8 text-slate-400" />
                    </div>
                    <p className="text-slate-500">No API tests run yet</p>
                    <p className="text-sm text-slate-400 mt-1">
                      Click a test button to start
                    </p>
                  </motion.div>
                ) : (
                  apiResults.map((result) => (
                    <motion.div
                      key={result.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -20 }}
                      transition={{ duration: 0.3 }}
                      className={`glass rounded-lg p-3 border-l-4 ${
                        result.success ? "border-green-400" : "border-red-400"
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <span
                            className={`px-2 py-0.5 text-xs font-medium rounded ${
                              result.method === "GET"
                                ? "bg-blue-100 text-blue-700"
                                : "bg-green-100 text-green-700"
                            }`}
                          >
                            {result.method}
                          </span>
                          <span className="text-sm font-medium text-slate-800">
                            {result.endpoint}
                          </span>
                        </div>
                        <span
                          className={`text-xs font-medium ${
                            result.success ? "text-green-600" : "text-red-600"
                          }`}
                        >
                          {result.status}
                        </span>
                      </div>

                      <div className="space-y-2">
                        <div>
                          <p className="text-xs font-medium text-slate-600 mb-1">
                            URL:
                          </p>
                          <p className="text-xs text-slate-700 bg-slate-50 rounded p-2 font-mono break-all">
                            {result.url}
                          </p>
                        </div>

                        <div>
                          <p className="text-xs font-medium text-slate-600 mb-1">
                            Response:
                          </p>
                          <pre
                            className={`text-xs rounded p-2 overflow-x-auto ${
                              result.success
                                ? "bg-green-50 text-green-800"
                                : "bg-red-50 text-red-800"
                            }`}
                          >
                            {JSON.stringify(result.data, null, 2)}
                          </pre>
                        </div>

                        <div className="flex items-center justify-between text-xs text-slate-500">
                          <span>{result.timestamp}</span>
                          <span>{result.responseTime}ms</span>
                        </div>
                      </div>
                    </motion.div>
                  ))
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Testing;
