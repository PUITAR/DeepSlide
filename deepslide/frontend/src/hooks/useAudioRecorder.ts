import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type RecorderStatus = 'idle' | 'recording' | 'stopped' | 'error';

export type UseAudioRecorderState = {
  status: RecorderStatus;
  seconds: number;
  lastBlob: Blob | null;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
};

const pickMimeType = (): string | undefined => {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
  for (const t of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t;
  }
  return undefined;
};

export const useAudioRecorder = (): UseAudioRecorderState => {
  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [seconds, setSeconds] = useState(0);
  const [lastBlob, setLastBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);

  const mimeType = useMemo(() => pickMimeType(), []);

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const cleanupStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  };

  const reset = useCallback(() => {
    clearTimer();
    cleanupStream();
    recorderRef.current = null;
    chunksRef.current = [];
    setSeconds(0);
    setLastBlob(null);
    setError(null);
    setStatus('idle');
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setLastBlob(null);
    setSeconds(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = (evt) => {
        if (evt.data && evt.data.size > 0) chunksRef.current.push(evt.data);
      };

      recorder.onerror = () => {
        setStatus('error');
        setError('Recording failed');
        clearTimer();
        cleanupStream();
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' });
        setLastBlob(blob.size > 0 ? blob : null);
        chunksRef.current = [];
        setStatus('stopped');
        clearTimer();
        cleanupStream();
      };

      recorder.start(250);
      setStatus('recording');
      timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      setStatus('error');
      setError('Microphone permission denied');
      clearTimer();
      cleanupStream();
    }
  }, [mimeType]);

  const stop = useCallback(() => {
    const r = recorderRef.current;
    if (r && r.state !== 'inactive') {
      r.stop();
    }
  }, []);

  useEffect(() => {
    return () => {
      clearTimer();
      cleanupStream();
    };
  }, []);

  return { status, seconds, lastBlob, error, start, stop, reset };
};
