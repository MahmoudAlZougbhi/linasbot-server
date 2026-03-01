import React, { useRef, useState } from "react";
import { getApiAbsoluteBaseUrl } from "../../utils/apiBaseUrl";

const getProxiedAudioUrl = (url) => {
  if (!url) return url;

  const isExternal =
    url.includes("whatsapp") ||
    url.includes("mmc.api.montymobile.com") ||
    url.includes("firebasestorage.googleapis.com") ||
    url.includes("mmg.whatsapp.net") ||
    (url.startsWith("http") && !url.includes(window.location.hostname));

  if (!isExternal) {
    return url;
  }

  const baseURL = getApiAbsoluteBaseUrl();
  return `${baseURL}/api/media/audio?url=${encodeURIComponent(url)}`;
};

const formatTime = (time) => {
  if (Number.isNaN(time)) return "0:00";
  const minutes = Math.floor(time / 60);
  const seconds = Math.floor(time % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
};

const ModernAudioPlayer = ({ audioUrl, isUserMessage = false }) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const audioRef = useRef(null);
  const proxiedAudioUrl = getProxiedAudioUrl(audioUrl);

  const handlePlayPause = () => {
    if (!audioRef.current || error) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch((playError) => {
        console.error("Audio play error:", playError);
        setError(true);
      });
    }
    setIsPlaying(!isPlaying);
  };

  const handleProgressChange = (event) => {
    const newTime = parseFloat(event.target.value);
    if (!audioRef.current) return;
    audioRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const progressRatio = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div
      className={`flex items-center space-x-2 py-1 px-2 rounded-full ${
        isUserMessage ? "bg-slate-200" : "bg-black bg-opacity-10"
      }`}
    >
      <button
        onClick={handlePlayPause}
        className={`flex-shrink-0 p-2 rounded-full transition-all hover:scale-110 ${
          isUserMessage
            ? "bg-slate-400 hover:bg-slate-500 text-white"
            : "bg-white bg-opacity-20 hover:bg-opacity-40 text-white"
        }`}
      >
        {isPlaying ? (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M5 4a1 1 0 00-1 1v10a1 1 0 001 1h2a1 1 0 001-1V5a1 1 0 00-1-1H5zm8 0a1 1 0 00-1 1v10a1 1 0 001 1h2a1 1 0 001-1V5a1 1 0 00-1-1h-2z"
              clipRule="evenodd"
            />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M5.75 1.172A.5.5 0 005 1.65v16.7a.5.5 0 00.75.478l10.67-8.35a.5.5 0 000-.796L5.75 1.172z" />
          </svg>
        )}
      </button>

      <div className="flex-1 flex flex-col space-y-1 min-w-[120px]">
        <input
          type="range"
          min="0"
          max={duration || 0}
          value={currentTime}
          onChange={handleProgressChange}
          className={`w-full h-1 rounded-full appearance-none cursor-pointer ${
            isUserMessage ? "bg-slate-300 accent-slate-600" : "bg-white bg-opacity-30 accent-white"
          }`}
          style={{
            background: isUserMessage
              ? `linear-gradient(to right, #475569 ${progressRatio}%, #cbd5e1 ${progressRatio}%)`
              : `linear-gradient(to right, white ${progressRatio}%, rgba(255,255,255,0.3) ${progressRatio}%)`,
          }}
        />
        <div className={`text-xs font-medium ${isUserMessage ? "text-slate-600" : "text-white"}`}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </div>
      </div>

      {error && (
        <span className={`text-xs ml-2 ${isUserMessage ? "text-red-600" : "text-red-400"}`}>
          Audio unavailable
        </span>
      )}

      {isLoading && !error && (
        <span className={`text-xs ml-2 ${isUserMessage ? "text-slate-500" : "opacity-50"}`}>
          Loading...
        </span>
      )}

      <audio
        ref={audioRef}
        src={proxiedAudioUrl}
        onLoadedMetadata={() => {
          if (audioRef.current) setDuration(audioRef.current.duration);
        }}
        onTimeUpdate={() => {
          if (audioRef.current) setCurrentTime(audioRef.current.currentTime);
        }}
        onEnded={() => {
          setIsPlaying(false);
          if (audioRef.current) {
            audioRef.current.currentTime = 0;
            setCurrentTime(0);
          }
        }}
        onError={(event) => {
          console.error("Audio load error:", event, "URL:", audioUrl);
          setError(true);
          setIsLoading(false);
        }}
        onCanPlay={() => {
          setIsLoading(false);
          setError(false);
        }}
      />
    </div>
  );
};

export default ModernAudioPlayer;
