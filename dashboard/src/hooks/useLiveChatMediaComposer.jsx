import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

/** @param {Blob} blob */
const blobToBase64 = (blob) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Unexpected file reader result"));
        return;
      }
      const parts = result.split(",");
      resolve(parts[1] || "");
    };
    reader.onerror = () => reject(new Error("Failed to convert blob to base64"));
    reader.readAsDataURL(blob);
  });

/**
 * @param {{
 *   selectedConversation: SelectedConversation | null;
 *   sendOperatorMessage: (
 *     conversationId: string,
 *     userId: string,
 *     message: string,
 *     operatorId: string,
 *     messageType?: string,
 *     idempotencyKey?: string | null
 *   ) => Promise<{ success?: boolean }>;
 *   onAppendMessage?: (message: LiveChatMessage) => void;
 * }} params
 */
export const useLiveChatMediaComposer = ({
  selectedConversation,
  sendOperatorMessage,
  onAppendMessage: _onAppendMessage,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState(/** @type {{ blob: Blob; url: string } | null} */ (null));
  const [recordingTime, setRecordingTime] = useState(0);
  const [isSendingVoice, setIsSendingVoice] = useState(false);
  const [selectedImage, setSelectedImage] = useState(/** @type {{ file: File; preview: string | ArrayBuffer | null; name: string } | null} */ (null));

  const mediaRecorderRef = useRef(/** @type {MediaRecorder | null} */ (null));
  const audioChunksRef = useRef(/** @type {Blob[]} */ ([]));
  const recordingIntervalRef = useRef(/** @type {ReturnType<typeof setInterval> | null} */ (null));
  const imageInputRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const sendingVoiceRef = useRef(false);
  const sendingImageRef = useRef(false);

  const clearRecordingInterval = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current);
      recordingIntervalRef.current = null;
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((/** @type {MediaStreamTrack} */ track) => track.stop());
      setIsRecording(false);
      clearRecordingInterval();
    }
  };

  useEffect(() => {
    return () => {
      clearRecordingInterval();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current.stream.getTracks().forEach((/** @type {MediaStreamTrack} */ track) => track.stop());
      }
      if (recordedAudio?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(recordedAudio.url);
      }
    };
  }, [recordedAudio]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (event) => audioChunksRef.current.push(event.data);
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const audioUrl = URL.createObjectURL(audioBlob);
        setRecordedAudio({ blob: audioBlob, url: audioUrl });
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);

      clearRecordingInterval();
      recordingIntervalRef.current = setInterval(() => {
        setRecordingTime((previous) => {
          if (previous >= 300) {
            stopRecording();
            return previous;
          }
          return previous + 1;
        });
      }, 1000);
    } catch (error) {
      console.error("Error accessing microphone:", error);
      toast.error("Could not access microphone");
    }
  };

  const discardRecording = () => {
    if (recordedAudio?.url?.startsWith("blob:")) {
      URL.revokeObjectURL(recordedAudio.url);
    }
    setRecordedAudio(null);
    setRecordingTime(0);
  };

  const sendVoiceMessage = async () => {
    if (!recordedAudio || !selectedConversation || isSendingVoice || sendingVoiceRef.current)
      return;

    sendingVoiceRef.current = true;
    setIsSendingVoice(true);
    const localRecordedAudio = recordedAudio;
    const idempotencyKey =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `voice_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

    try {
      const base64Audio = await blobToBase64(recordedAudio.blob);
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        base64Audio,
        "operator_001",
        "voice",
        idempotencyKey
      );

      if (!result.success) {
        toast.error("Failed to send voice message");
        return;
      }

      // Message will appear via SSE (no manual append to avoid duplicate)
      if (localRecordedAudio?.url?.startsWith("blob:")) {
        URL.revokeObjectURL(localRecordedAudio.url);
      }
      setRecordedAudio(null);
      setRecordingTime(0);
      toast.success("Voice message sent to customer");
    } catch (error) {
      console.error("Error sending voice message:", error);
      toast.error("Error sending voice message");
    } finally {
      setIsSendingVoice(false);
      sendingVoiceRef.current = false;
    }
  };

  /** @param {import('react').ChangeEvent<HTMLInputElement>} event */
  const handleImageSelect = (event) => {
    const file = event.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) {
      toast.error("Please select a valid image file");
      return;
    }

    const reader = new FileReader();
    reader.onload = (readerEvent) => {
      setSelectedImage({
        file,
        preview: typeof readerEvent.target?.result === 'string' ? readerEvent.target.result : null,
        name: file.name,
      });
    };
    reader.readAsDataURL(file);
  };

  const discardImage = () => {
    setSelectedImage(null);
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
  };

  const sendImageMessage = async () => {
    if (!selectedImage || !selectedConversation || sendingImageRef.current) return;

    sendingImageRef.current = true;
    const idempotencyKey =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `img_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

    try {
      const base64Image = String(selectedImage.preview || "").split(",")[1] || "";
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        base64Image,
        "operator_001",
        "image",
        idempotencyKey
      );

      if (!result.success) {
        toast.error("Failed to send image");
        return;
      }

      // Message will appear via SSE (no manual append to avoid duplicate)
      discardImage();
      toast.success("Image sent to customer");
    } catch (error) {
      console.error("Error sending image:", error);
      toast.error("Error sending image");
    } finally {
      sendingImageRef.current = false;
    }
  };

  /** @param {number} seconds */
  const formatRecordingTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return {
    isRecording,
    recordedAudio,
    recordingTime,
    isSendingVoice,
    selectedImage,
    imageInputRef,
    startRecording,
    stopRecording,
    discardRecording,
    sendVoiceMessage,
    formatRecordingTime,
    handleImageSelect,
    discardImage,
    sendImageMessage,
  };
};
