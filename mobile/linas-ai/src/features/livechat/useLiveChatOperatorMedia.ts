import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { readAsStringAsync } from 'expo-file-system/legacy';
import { getInfoAsync } from 'expo-file-system/legacy';
import { useRef, useState } from 'react';

type VoicePhase = 'idle' | 'recording';

const VOICE_PRESET = {
  ...RecordingPresets.HIGH_QUALITY,
  isMeteringEnabled: false,
  numberOfChannels: 1,
  bitRate: 64000,
};

async function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

async function uriToBase64(uri: string): Promise<string> {
  return readAsStringAsync(uri, { encoding: 'base64' });
}

export function useLiveChatOperatorMedia() {
  const recorder = useAudioRecorder(VOICE_PRESET);
  useAudioRecorderState(recorder, 120);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>('idle');
  const [mediaError, setMediaError] = useState<string | null>(null);
  const busyRef = useRef(false);

  async function pickImageBase64(): Promise<string | null> {
    setMediaError(null);
    try {
      const ImagePicker = require('expo-image-picker') as typeof import('expo-image-picker');
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setMediaError('Photo access is required to send images.');
        return null;
      }
      const picked = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.85,
        base64: true,
      });
      if (picked.canceled || !picked.assets?.length) return null;
      const asset = picked.assets[0];
      if (asset.base64) return asset.base64;
      if (asset.uri) return uriToBase64(asset.uri);
      return null;
    } catch (err) {
      setMediaError(err instanceof Error ? err.message : 'Could not pick image.');
      return null;
    }
  }

  async function startVoiceRecording() {
    if (busyRef.current || voicePhase === 'recording') return;
    busyRef.current = true;
    setMediaError(null);
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setMediaError('Microphone permission is required for voice messages.');
        return;
      }
      await setAudioModeAsync({
        playsInSilentMode: true,
        allowsRecording: true,
        interruptionMode: 'doNotMix',
      });
      await recorder.prepareToRecordAsync();
      recorder.record();
      for (let i = 0; i < 10 && !recorder.isRecording; i++) {
        await sleep(30);
      }
      if (!recorder.isRecording) {
        throw new Error('Could not start microphone.');
      }
      setVoicePhase('recording');
    } catch (err) {
      setMediaError(err instanceof Error ? err.message : 'Could not start recording.');
      setVoicePhase('idle');
    } finally {
      busyRef.current = false;
    }
  }

  async function stopVoiceRecording(): Promise<string | null> {
    if (voicePhase !== 'recording') return null;
    busyRef.current = true;
    setMediaError(null);
    try {
      const duration = recorder.getStatus().durationMillis;
      if (duration < 500) {
        await sleep(500 - duration);
      }
      await recorder.stop();
      for (let attempt = 0; attempt < 8; attempt++) {
        const status = recorder.getStatus();
        const uri = (recorder.uri || status.url || '').trim();
        if (uri) {
          const info = await getInfoAsync(uri);
          if (info.exists && !info.isDirectory) {
            return uriToBase64(uri);
          }
        }
        await sleep(60);
      }
      throw new Error('No voice captured. Hold longer, then send.');
    } catch (err) {
      setMediaError(err instanceof Error ? err.message : 'Could not send voice.');
      return null;
    } finally {
      setVoicePhase('idle');
      busyRef.current = false;
      try {
        await setAudioModeAsync({
          allowsRecording: false,
          playsInSilentMode: true,
          interruptionMode: 'mixWithOthers',
        });
      } catch {
        // ignore
      }
    }
  }

  async function cancelVoiceRecording() {
    if (voicePhase !== 'recording') return;
    try {
      await recorder.stop();
    } catch {
      // ignore
    }
    setVoicePhase('idle');
    setMediaError(null);
    try {
      await setAudioModeAsync({
        allowsRecording: false,
        playsInSilentMode: true,
        interruptionMode: 'mixWithOthers',
      });
    } catch {
      // ignore
    }
  }

  return {
    voicePhase,
    mediaError,
    pickImageBase64,
    startVoiceRecording,
    stopVoiceRecording,
    cancelVoiceRecording,
    isRecordingVoice: voicePhase === 'recording',
  };
}
