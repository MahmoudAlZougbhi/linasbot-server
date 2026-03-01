import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

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

export const useLiveChatMediaComposer = ({
  selectedConversation,
  sendOperatorMessage,
  onAppendMessage,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [isSendingVoice, setIsSendingVoice] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordingIntervalRef = useRef(null);
  const imageInputRef = useRef(null);

  const clearRecordingInterval = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current);
      recordingIntervalRef.current = null;
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
      setIsRecording(false);
      clearRecordingInterval();
    }
  };

  useEffect(() => {
    return () => {
      clearRecordingInterval();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
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
    if (!recordedAudio || !selectedConversation || isSendingVoice) return;

    setIsSendingVoice(true);
    const localRecordedAudio = recordedAudio;

    try {
      const base64Audio = await blobToBase64(recordedAudio.blob);
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        base64Audio,
        "operator_001",
        "voice"
      );

      if (!result.success) {
        toast.error("Failed to send voice message");
        return;
      }

      const persistedAudioUrl =
        result.storage_url || result.whatsapp_audio_url || localRecordedAudio.url;

      onAppendMessage({
        timestamp: new Date().toISOString(),
        is_user: false,
        content: "[رسالة صوتية]",
        text: "[رسالة صوتية]",
        type: "voice",
        audio_url: persistedAudioUrl,
        handled_by: "human",
      });

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
    }
  };

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
        preview: readerEvent.target?.result,
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
    if (!selectedImage || !selectedConversation) return;

    try {
      const base64Image = String(selectedImage.preview || "").split(",")[1] || "";
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        base64Image,
        "operator_001",
        "image"
      );

      if (!result.success) {
        toast.error("Failed to send image");
        return;
      }

      onAppendMessage({
        timestamp: new Date().toISOString(),
        is_user: false,
        content: "[صورة]",
        type: "image",
        image_url: selectedImage.preview,
        handled_by: "human",
      });
      discardImage();
      toast.success("Image sent to customer");
    } catch (error) {
      console.error("Error sending image:", error);
      toast.error("Error sending image");
    }
  };

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
