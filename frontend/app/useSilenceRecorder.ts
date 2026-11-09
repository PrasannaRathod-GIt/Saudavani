"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ---- tunables --------------------------------------------------------------------------------
export const SILENCE_STOP_MS = 2200;      // silence AFTER speech that ends the recording
const NO_SPEECH_TIMEOUT_MS = 10000;       // never speaks at all -> discard, no submission
const MAX_RECORDING_MS = 60000;           // hard safety cap
const CALIBRATION_MS = 400;               // measure room noise first (no stopping during this)
const MIN_SPEECH_MS = 200;                // voiced time needed to call it "speech"
const SHOW_FINISHING_AFTER_MS = 800;      // show "finishing" UI before the 2.2 s elapses
const MIN_BLOB_BYTES = 1000;              // smaller than this = empty recording
const POLL_MS = 50;

export type RecState = "idle" | "listening" | "speech" | "finishing" | "processing" | "error";
export const REC_LABEL: Record<RecState, string> = {
  idle: "", listening: "Listening…", speech: "Speech detected",
  finishing: "Silence detected – finishing recording", processing: "Processing…", error: "Recording error",
};

type Rt = {
  stream: MediaStream | null;
  ctx: AudioContext | null;
  source: MediaStreamAudioSourceNode | null;
  analyser: AnalyserNode | null;
  recorder: MediaRecorder | null;
  chunks: Blob[];
  timer: ReturnType<typeof setInterval> | null;
  starting: boolean;
  active: boolean;
  stopping: boolean;
  discard: boolean;
  mime: string;
};

export function useSilenceRecorder(onComplete: (blob: Blob, mimeType: string) => Promise<void> | void) {
  const [state, setState] = useState<RecState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audioFeatures, setAudioFeatures] = useState<{
    echoCancellation?: boolean;
    noiseSuppression?: boolean;
    autoGainControl?: boolean;
  } | null>(null);
  const [autoStopAvailable, setAutoStopAvailable] = useState(true);
  const cbRef = useRef(onComplete);
  const unmounted = useRef(false);
  const rt = useRef<Rt>({
    stream: null,
    ctx: null,
    source: null,
    analyser: null,
    recorder: null,
    chunks: [],
    timer: null,
    starting: false,
    active: false,
    stopping: false,
    discard: false,
    mime: "",
  });

  useEffect(() => {
    cbRef.current = onComplete;
  }, [onComplete]);

  const releaseAudio = useCallback(() => {
    const x = rt.current;
    if (x.timer) {
      clearInterval(x.timer);
      x.timer = null;
    }
    try { x.source?.disconnect(); } catch { /* already disconnected */ }
    try { x.analyser?.disconnect(); } catch { /* already disconnected */ }
    x.source = null;
    x.analyser = null;
    if (x.ctx && x.ctx.state !== "closed") x.ctx.close().catch(() => {});
    x.ctx = null;
    x.stream?.getTracks().forEach((track) => track.stop());
    x.stream = null;
  }, []);

  const fail = useCallback((message: string) => {
    const x = rt.current;
    releaseAudio();
    x.active = false;
    x.stopping = false;
    x.starting = false;
    x.recorder = null;
    x.chunks = [];
    if (!unmounted.current) {
      setError(message);
      setState("error");
    }
  }, [releaseAudio]);

  const finish = useCallback((reason: "manual" | "silence" | "max" | "no_speech") => {
    const x = rt.current;
    if (!x.active || x.stopping) return; // idempotent: manual + silence + max can race safely
    x.stopping = true;
    x.discard = reason === "no_speech";
    if (x.timer) {
      clearInterval(x.timer);
      x.timer = null;
    }
    if (!unmounted.current && reason !== "no_speech") setState("finishing");
    const recorder = x.recorder;
    if (recorder && recorder.state !== "inactive") {
      try { recorder.stop(); } catch { fail("Could not stop the recorder."); }
    } else {
      fail("Recorder was not running.");
    }
  }, [fail]);

  const start = useCallback(async () => {
    const x = rt.current;
    if (x.active || x.starting) return;
    x.starting = true;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      x.starting = false;
      setError("This browser cannot record audio.");
      setState("error");
      return;
    }

    let stream: MediaStream;
    try {
      const wanted: MediaTrackConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      };
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: wanted });
      } catch (caught) {
        const name = caught instanceof DOMException ? caught.name : "";
        if (name === "OverconstrainedError" || name === "ConstraintNotSatisfiedError") {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } else {
          throw caught;
        }
      }
    } catch (caught) {
      x.starting = false;
      const name = caught instanceof DOMException ? caught.name : "";
      setError(
        name === "NotAllowedError" || name === "SecurityError"
          ? "Microphone permission was denied."
          : name === "NotFoundError" || name === "NotReadableError"
            ? "No usable microphone was found."
            : "Could not open the microphone."
      );
      setState("error");
      return;
    }

    if (unmounted.current) {
      stream.getTracks().forEach((track) => track.stop());
      x.starting = false;
      return;
    }
    x.stream = stream;

    // Report the browser settings actually applied; do not assume constraints were honored.
    const settings = stream.getAudioTracks()[0]?.getSettings?.();
    setAudioFeatures(settings ? {
      echoCancellation: settings.echoCancellation,
      noiseSuppression: settings.noiseSuppression,
      autoGainControl: settings.autoGainControl,
    } : null);

    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(
      (candidate) => MediaRecorder.isTypeSupported?.(candidate)
    ) || "";
    let recorder: MediaRecorder;
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch {
      x.starting = false;
      fail("Could not start the recorder.");
      return;
    }

    x.recorder = recorder;
    x.chunks = [];
    x.mime = recorder.mimeType || mime || "audio/webm";
    x.stopping = false;
    x.discard = false;

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) x.chunks.push(event.data);
    };
    recorder.onerror = () => fail("Recorder error. Please try again.");
    recorder.onstop = async () => {
      const chunks = x.chunks;
      const mimeType = x.mime;
      const discard = x.discard;
      releaseAudio();
      x.active = false;
      x.stopping = false;
      x.recorder = null;
      x.chunks = [];
      if (unmounted.current) return;
      if (discard) {
        setError("No speech was heard. Tap the mic and try again.");
        setState("error");
        return;
      }
      const blob = new Blob(chunks, { type: mimeType });
      if (blob.size < MIN_BLOB_BYTES) {
        setError("The recording was empty. Please try again.");
        setState("error");
        return;
      }
      setState("processing");
      try {
        await cbRef.current(blob, mimeType);
        if (!unmounted.current) setState("idle");
      } catch {
        if (!unmounted.current) {
          setError("Could not process the recording.");
          setState("error");
        }
      }
    };

    // Web Audio level meter is never connected to speakers. If unavailable, manual stop remains available.
    let analyser: AnalyserNode | null = null;
    try {
      const AudioContextConstructor = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextConstructor) throw new Error("Web Audio is unavailable");
      const context = new AudioContextConstructor();
      if (context.state === "suspended") await context.resume();
      const source = context.createMediaStreamSource(stream);
      analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      x.ctx = context;
      x.source = source;
      x.analyser = analyser;
      setAutoStopAvailable(true);
    } catch {
      setAutoStopAvailable(false); // safe fallback: never cut the farmer off
    }

    x.active = true;
x.starting = false;

try {
  recorder.start(250);
  setState("listening");
} catch {
  fail("Could not start the recorder.");
  return;
}

const startedAt = performance.now();

if (!analyser) {
  // Keep the 60-second safety limit even if automatic silence detection is unavailable.
  x.timer = setInterval(() => {
    if (!x.active || x.stopping) return;

    if (performance.now() - startedAt >= MAX_RECORDING_MS) {
      finish("max");
    }
  }, POLL_MS);

  return;
}

    const buffer = new Float32Array(analyser.fftSize);
    let previousAt = startedAt;
    let calibrated = false;
    let speechDetected = false;
    let voicedMs = 0;
    let lastVoiceAt = startedAt;
    const calibration: number[] = [];
    let speechThreshold = 0.02;
    let silenceThreshold = 0.012;
    let uiState: RecState = "listening";
    const show = (next: RecState) => {
      if (next !== uiState) {
        uiState = next;
        setState(next);
      }
    };

    x.timer = setInterval(() => {
      if (!x.active || x.stopping || !x.analyser) return;
      x.analyser.getFloatTimeDomainData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
      const rms = Math.sqrt(sum / buffer.length);
      const now = performance.now();
      const delta = now - previousAt;
      previousAt = now;
      const elapsed = now - startedAt;

      if (elapsed > MAX_RECORDING_MS) return finish("max");

      if (!calibrated) {
        calibration.push(rms);
        if (elapsed >= CALIBRATION_MS || rms > 0.08) {
          if (elapsed >= CALIBRATION_MS) {
            const sorted = [...calibration].sort((a, b) => a - b);
            const noiseFloor = Math.min(0.03, sorted[Math.floor(sorted.length / 2)]);
            speechThreshold = Math.max(0.02, noiseFloor * 2.5);
            silenceThreshold = Math.max(0.012, noiseFloor * 1.6);
          }
          calibrated = true;
        } else {
          return;
        }
      }

      if (!speechDetected) {
        voicedMs = rms >= speechThreshold ? voicedMs + delta : 0;
        if (voicedMs >= MIN_SPEECH_MS) {
          speechDetected = true;
          lastVoiceAt = now;
          show("speech");
        } else if (elapsed > NO_SPEECH_TIMEOUT_MS) {
          finish("no_speech");
        }
        return;
      }

      if (rms >= silenceThreshold) {
        lastVoiceAt = now;
        show("speech");
      } else {
        const silentFor = now - lastVoiceAt;
        if (silentFor >= SILENCE_STOP_MS) finish("silence");
        else if (silentFor >= SHOW_FINISHING_AFTER_MS) show("finishing");
      }
    }, POLL_MS);
  }, [fail, finish, releaseAudio]);

  const stop = useCallback(() => finish("manual"), [finish]); // manual stop always works

  useEffect(() => {
    unmounted.current = false;
    const x = rt.current;
    return () => {
      unmounted.current = true;
      x.discard = true; // never submit after unmount
      if (x.recorder) {
        x.recorder.ondataavailable = null;
        x.recorder.onstop = null;
        x.recorder.onerror = null;
        try {
          if (x.recorder.state !== "inactive") x.recorder.stop();
        } catch { /* component is already unmounting */ }
      }
      releaseAudio();
      x.active = false;
      x.stopping = false;
      x.starting = false;
      x.recorder = null;
      x.chunks = [];
    };
  }, [releaseAudio]);

  return {
    state,
    error,
    start,
    stop,
    isRecording: state === "listening" || state === "speech" || state === "finishing",
    audioFeatures,
    autoStopAvailable,
  };
}
