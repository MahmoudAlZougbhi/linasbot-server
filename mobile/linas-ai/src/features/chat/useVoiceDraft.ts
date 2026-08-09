import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { getInfoAsync } from 'expo-file-system/legacy';
import { useEffect, useRef, useState } from 'react';

import { apiUpload, ApiError } from '../../api/client';
import { appendLocalFile } from '../../api/formDataFile';

export type VoiceState = 'idle' | 'recording' | 'transcribing';

const VOICE_PRESET = {
  ...RecordingPresets.HIGH_QUALITY,
  isMeteringEnabled: true,
  numberOfChannels: 1,
  bitRate: 64000,
};

function extensionForUri(uri: string): string {
  const match = /\.([a-z0-9]+)(?:\?|$)/i.exec(uri);
  return match?.[1]?.toLowerCase() ?? 'm4a';
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: string; error?: string } | null;
    if (body?.detail) return String(body.detail);
    if (body?.error) return String(body.error);
    if (err.status === 401) return 'Please sign in again to use voice.';
    if (err.message) return err.message;
  }
  if (err instanceof Error && err.message) {
    if (/unsupported form data part/i.test(err.message)) {
      return 'Voice upload failed (FormData). Rebuild the app and try again.';
    }
    return err.message;
  }
  return 'Could not transcribe. Try again or type your message.';
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

export function useVoiceDraft(onText: (text: string) => void) {
  const recorder = useAudioRecorder(VOICE_PRESET);
  const recorderState = useAudioRecorderState(recorder, 120);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const stateRef = useRef<VoiceState>('idle');
  const busyRef = useRef(false);
  const startedAtRef = useRef(0);
  const onTextRef = useRef(onText);

  useEffect(() => {
    onTextRef.current = onText;
  }, [onText]);

  function setState(next: VoiceState) {
    stateRef.current = next;
    setVoiceState(next);
  }

  async function resolveRecordingUri(): Promise<string> {
    for (let attempt = 0; attempt < 8; attempt++) {
      const status = recorder.getStatus();
      const uri = (recorder.uri || status.url || '').trim();
      if (uri) {
        try {
          const info = await getInfoAsync(uri);
          if (info.exists && !info.isDirectory) {
            const size = 'size' in info && typeof info.size === 'number' ? info.size : 0;
            if (size > 0) return uri;
          }
        } catch {
          // URI may still be valid for FormData even if getInfoAsync fails.
          return uri;
        }
      }
      await sleep(60);
    }
    throw new Error('No recording captured. Hold a moment longer, then stop.');
  }

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
      interruptionMode: 'doNotMix',
    });
    await recorder.prepareToRecordAsync();
    recorder.record();
    // Native isRecording can lag a tick after record().
    for (let i = 0; i < 10 && !recorder.isRecording; i++) {
      await sleep(30);
    }
    if (!recorder.isRecording) {
      throw new Error('Could not start microphone. Check permission and try again.');
    }
    startedAtRef.current = Date.now();
    setState('recording');
  }

  async function stopAndTranscribe() {
    setState('transcribing');
    try {
      const elapsed = Date.now() - startedAtRef.current;
      if (elapsed < 500) {
        await sleep(500 - elapsed);
      }
      await recorder.stop();
      const uri = await resolveRecordingUri();
      const ext = extensionForUri(uri);
      const buildForm = () => {
        const form = new FormData();
        // Must use expo-file-system File — RN uri object parts break expo/fetch.
        appendLocalFile(form, 'audio', uri, { name: `voice.${ext}` });
        return form;
      };

      const response = await apiUpload('/api/mobile/transcribe', buildForm);
      let body: { success?: boolean; text?: string; detail?: string; error?: string } = {};
      try {
        body = (await response.json()) as typeof body;
      } catch {
        throw new Error('Transcription server returned an invalid response.');
      }
      if (!response.ok) {
        throw new ApiError(
          body.detail || body.error || 'Transcription failed',
          response.status,
          body,
        );
      }
      const text = (body.text || '').trim();
      if (!text) {
        throw new Error('No speech detected. Try again.');
      }
      // Insert into composer only — never auto-send.
      setVoiceError(null);
      onTextRef.current(text);
    } finally {
      setState('idle');
      try {
        await setAudioModeAsync({
          allowsRecording: false,
          playsInSilentMode: true,
          interruptionMode: 'mixWithOthers',
        });
      } catch {
        // ignore mode reset failures
      }
    }
  }

  async function toggleVoice() {
    if (busyRef.current || stateRef.current === 'transcribing') {
      return;
    }
    busyRef.current = true;
    try {
      if (stateRef.current === 'recording') {
        await stopAndTranscribe();
        return;
      }
      if (stateRef.current === 'idle') {
        await startRecording();
      }
    } catch (err) {
      setState('idle');
      setVoiceError(errorMessage(err));
      try {
        if (recorder.isRecording) {
          await recorder.stop();
        }
      } catch {
        // ignore cleanup
      }
    } finally {
      busyRef.current = false;
    }
  }

  return {
    voiceState,
    voiceError,
    toggleVoice,
    metering: voiceState === 'recording' ? (recorderState.metering ?? null) : null,
    isRecording: voiceState === 'recording' || recorderState.isRecording,
  };
}
