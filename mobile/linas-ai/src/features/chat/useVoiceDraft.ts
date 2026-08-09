import { Audio } from 'expo-av';
import { useRef, useState } from 'react';

import { API_BASE } from '../../config';
import { tokenStore } from '../../auth/tokenStore';

type VoiceState = 'idle' | 'recording' | 'transcribing';

export function useVoiceDraft(onText: (text: string) => void) {
  const recordingRef = useRef<Audio.Recording | null>(null);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);

  async function startRecording() {
    setVoiceError(null);
    const permission = await Audio.requestPermissionsAsync();
    if (!permission.granted) {
      setVoiceError('Microphone permission is required for voice messages.');
      return;
    }
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
    });
    const recording = new Audio.Recording();
    await recording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
    await recording.startAsync();
    recordingRef.current = recording;
    setVoiceState('recording');
  }

  async function stopAndTranscribe() {
    const recording = recordingRef.current;
    if (!recording) {
      return;
    }
    setVoiceState('transcribing');
    try {
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      recordingRef.current = null;
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
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
    }
  }

  async function toggle() {
    if (voiceState === 'recording') {
      await stopAndTranscribe();
      return;
    }
    if (voiceState === 'idle') {
      await startRecording();
    }
  }

  return { voiceState, voiceError, toggleVoice: toggle };
}
