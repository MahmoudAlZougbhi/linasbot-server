import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import { useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import { API_BASE } from '../../config';

type VoiceState = 'idle' | 'recording' | 'transcribing';

export function useVoiceDraft(onText: (text: string) => void) {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);

  async function startRecording() {
    setVoiceError(null);
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setVoiceError('Microphone permission is required for voice messages.');
      return;
    }
    await setAudioModeAsync({
      playsInSilentMode: true,
      allowsRecording: true,
    });
    await recorder.prepareToRecordAsync();
    recorder.record();
    setVoiceState('recording');
  }

  async function stopAndTranscribe() {
    setVoiceState('transcribing');
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) {
        throw new Error('No recording');
      }
      const access = await tokenStore.getAccessToken();
      if (!access) {
        throw new Error('Not authenticated');
      }
      const form = new FormData();
      form.append('audio', {
        uri,
        name: 'voice.m4a',
        type: 'audio/m4a',
      } as unknown as Blob);
      const response = await fetch(`${API_BASE}/api/mobile/transcribe`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${access}`, Accept: 'application/json' },
        body: form,
      });
      const body = (await response.json()) as { success?: boolean; text?: string; detail?: string };
      if (!response.ok || !body.text) {
        throw new Error(body.detail ?? 'Transcription failed');
      }
      onText(body.text);
    } catch {
      setVoiceError('Could not transcribe. Try again or type your message.');
    } finally {
      setVoiceState('idle');
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    }
  }

  async function toggleVoice() {
    if (voiceState === 'recording') {
      await stopAndTranscribe();
      return;
    }
    if (voiceState === 'idle') {
      await startRecording();
    }
  }

  return { voiceState, voiceError, toggleVoice };
}
