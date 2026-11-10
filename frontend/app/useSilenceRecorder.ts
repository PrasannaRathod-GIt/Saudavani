"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ---- tunables --------------------------------------------------------------------------------
// Silence (after confirmed speech) that ends the recording. Override without code changes via
// NEXT_PUBLIC_SILENCE_STOP_MS in frontend/.env.local (accepted range 1200-5000).
const ENV_SILENCE_MS = Number(process.env.NEXT_PUBLIC_SILENCE_STOP_MS);
export const SILENCE_STOP_MS =
  Number.isFinite(ENV_SILENCE_MS) && ENV_SILENCE_MS >= 1200 && ENV_SILENCE_MS <= 5000
    ? ENV_SILENCE_MS
    : 2000;
const DEBUG = process.env.NEXT_PUBLIC_RECORDER_DEBUG === "1"; // console.debug levels while tuning

const NO_SPEECH_TIMEOUT_MS = 10000;   // never speaks at all -> discard, no submission
const MAX_RECORDING_MS = 60000;       // hard safety cap
const CALIBRATION_MS = 400;           // measure room noise first (no stopping during this)
const MIN_SPEECH_MS = 200;            // sustained voiced time needed to call it "speech"
const EXTEND_CONFIRM_MS = 150;        // sustained sound needed to extend a recording after speech
const SHOW_FINISHING_AFTER_MS = 800;  // show "finishing" UI before the silence timer elapses
const MIN_BLOB_BYTES = 1000;          // smaller than this = empty recording
const POLL_MS = 50;
const MEDIAN_WINDOW = 5;              // median of last 5 frames (~250 ms) rejects 1-2 frame spikes
const ANALYSIS_BLOCKED_MS = 1500;     // AudioContext not running this long -> manual-stop mode
const DEAD_ANALYSER_MS = 1500;        // analyser returns only exact zeros this long -> manual-stop mode

// RMS thresholds (0..1 float samples)
const START_MIN = 0.014;              // absolute floor for speech start (keeps quiet voices detectable)
const END_MIN = 0.009;                // absolute floor for speech end (hysteresis: end < start)
const START_RATIO = 3.0;              // speech start = noise floor x 3
const END_RATIO = 1.7;                // speech end   = noise floor x 1.7
const NOISE_FLOOR_MAX = 0.025;        // never let calibration inflate the floor beyond this
const RELATIVE_END_RATIO = 0.15;      // sound must be > 15% of the farmer's own level to extend
const END_MAX = 0.04;                 // cap on the relative term so quiet trailing speech survives

export type RecState = "idle" | "listening" | "speech" | "finishing" | "processing" | "error";
export const REC_LABEL: Record<RecState, string> = {
  idle: "", listening: "Listening…", speech: "Speech detected",
  finishing: "Silence detected – finishing recording", processing: "Processing…", error: "Recording error",
};

const NO_SPEECH_MESSAGE = "No speech was heard. Move closer to the phone, tap the mic and try again.";
const INTERRUPTED_MESSAGE = "Recording was interrupted (another app or call may have taken the microphone). Tap the mic to try again.";
const BACKGROUND_MESSAGE = "Recording stopped because the app went to the background. Tap the mic to try again.";

type Rt = {
  stream: MediaStream | null;
  ctx: AudioContext | null;
  source: MediaStreamAudioSourceNode | null;
  nodes: AudioNode[];
  analyser: AnalyserNode | null;
  recorder: MediaRecorder | null;
  chunks: Blob[];
  timer: ReturnType<typeof setInterval> | null;
  starting: boolean;
  active: boolean;
  stopping: boolean;
  discard: boolean;
  discardMessage: string | null;
  mime: string;
  cleanups: Array<() => void>;
};

// ---- helpers ---------------------------------------------------------------------------------
function errorName(caught: unknown): string {
  return (caught as { name?: string } | null)?.name ?? "";
}

function micErrorMessage(name: string): string {
  switch (name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
      return "Microphone permission was denied. Allow microphone access for this site in your browser settings, then tap the mic again.";
    case "SecurityError":
      return "The browser blocked microphone access. Open the app over HTTPS and allow the microphone.";
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "No microphone was found on this device.";
    case "NotReadableError":
    case "TrackStartError":
    case "AbortError":
      return "The microphone is busy or unavailable. Close other apps that may be using it and try again.";
    default:
      return "Could not open the microphone.";
  }
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// iOS (every iOS browser is WebKit) and desktop Safari record most reliably as MP4/AAC.
function prefersMp4(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const ios = /iP(hone|ad|od)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const desktopSafari = /Safari/.test(ua) && !/Chrome|Chromium|Edg|OPR|Android/.test(ua);
  return ios || desktopSafari;
}

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  const webm = ["audio/webm;codecs=opus", "audio/webm"];
  const mp4 = ["audio/mp4;codecs=mp4a.40.2", "audio/mp4", "audio/aac"];
  const ogg = ["audio/ogg;codecs=opus"];
  const order = prefersMp4() ? [...mp4, ...webm, ...ogg] : [...webm, ...mp4, ...ogg];
  return order.find((candidate) => {
    try { return MediaRecorder.isTypeSupported(candidate); } catch { return false; }
  }) ?? "";
}

function fallbackMime(): string {
  return prefersMp4() ? "audio/mp4" : "audio/webm";
}

// "ideal" constraints never cause OverconstrainedError, so unsupported options cannot block startup.
function buildAudioConstraints(): MediaTrackConstraints | true {
  const supported = navigator.mediaDevices.getSupportedConstraints?.() ?? {};
  const constraints: MediaTrackConstraints = {};
  if (supported.echoCancellation) constraints.echoCancellation = { ideal: true };
  if (supported.noiseSuppression) constraints.noiseSuppression = { ideal: true };
  if (supported.autoGainControl) constraints.autoGainControl = { ideal: true };
  if (supported.channelCount) constraints.channelCount = { ideal: 1 };
  return Object.keys(constraints).length > 0 ? constraints : true;
}

async function openMicrophone(): Promise<MediaStream> {
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: buildAudioConstraints() });
  } catch (caught) {
    const name = errorName(caught);
    if (name === "OverconstrainedError" || name === "ConstraintNotSatisfiedError" || name === "TypeError") {
      return await navigator.mediaDevices.getUserMedia({ audio: true }); // last resort: plain mic
    }
    throw caught;
  }
}

async function resumeWithTimeout(ctx: AudioContext, ms: number): Promise<void> {
  try {
    await Promise.race([ctx.resume(), new Promise<void>((resolve) => setTimeout(resolve, ms))]);
  } catch { /* the polling loop falls back to manual-stop mode if it never runs */ }
}

// ---- hook ------------------------------------------------------------------------------------
export function useSilenceRecorder(
  onComplete: (blob: Blob, mimeType: string) => Promise<void> | void,
  options?: { silenceStopMs?: number },
) {
  const [state, setState] = useState<RecState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audioFeatures, setAudioFeatures] = useState<{
    echoCancellation?: boolean;
    noiseSuppression?: boolean;
    autoGainControl?: boolean;
  } | null>(null);
  const [autoStopAvailable, setAutoStopAvailable] = useState(true);
  const cbRef = useRef(onComplete);
  const silenceRef = useRef(options?.silenceStopMs ?? SILENCE_STOP_MS);
  const unmounted = useRef(false);
  const rt = useRef<Rt>({
    stream: null,
    ctx: null,
    source: null,
    nodes: [],
    analyser: null,
    recorder: null,
    chunks: [],
    timer: null,
    starting: false,
    active: false,
    stopping: false,
    discard: false,
    discardMessage: null,
    mime: "",
    cleanups: [],
  });

  useEffect(() => {
    cbRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    silenceRef.current = options?.silenceStopMs ?? SILENCE_STOP_MS;
  }, [options?.silenceStopMs]);

  const releaseAudio = useCallback(() => {
    const x = rt.current;
    if (x.timer) {
      clearInterval(x.timer);
      x.timer = null;
    }
    x.cleanups.forEach((fn) => { try { fn(); } catch { /* listener already gone */ } });
    x.cleanups = [];
    try { x.source?.disconnect(); } catch { /* already disconnected */ }
    x.nodes.forEach((node) => { try { node.disconnect(); } catch { /* already disconnected */ } });
    try { x.analyser?.disconnect(); } catch { /* already disconnected */ }
    x.source = null;
    x.nodes = [];
    x.analyser = null;
    if (x.ctx && x.ctx.state !== "closed") x.ctx.close().catch(() => {});
    x.ctx = null;
    x.stream?.getTracks().forEach((track) => track.stop());
    x.stream = null;
  }, []);

  const fail = useCallback((message: string) => {
    const x = rt.current;
    const recorder = x.recorder;
    x.recorder = null;
    if (recorder) {
      // Detach first so a late "stop"/"error" event cannot submit audio or overwrite this message.
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.onerror = null;
      try { if (recorder.state !== "inactive") recorder.stop(); } catch { /* already stopped */ }
    }
    releaseAudio();
    x.active = false;
    x.stopping = false;
    x.starting = false;
    x.chunks = [];
    x.discard = false;
    x.discardMessage = null;
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
    x.discardMessage = reason === "no_speech" ? NO_SPEECH_MESSAGE : null;
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

  // Interruption (track ended, page hidden): stop and DISCARD the partial audio, show a message.
  const abort = useCallback((message: string) => {
    const x = rt.current;
    if (!x.active || x.stopping) return;
    x.stopping = true;
    x.discard = true;
    x.discardMessage = message;
    if (x.timer) {
      clearInterval(x.timer);
      x.timer = null;
    }
    const recorder = x.recorder;
    if (recorder && recorder.state !== "inactive") {
      try { recorder.stop(); } catch { fail(message); }
    } else {
      fail(message);
    }
  }, [fail]);

  const start = useCallback(async () => {
    const x = rt.current;
    if (x.active || x.starting) return;
    x.starting = true;
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      fail(window.isSecureContext
        ? "This browser cannot access the microphone."
        : "Microphone access needs a secure (HTTPS) connection. Open the app over HTTPS.");
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      fail("This browser cannot record audio. Please update your browser.");
      return;
    }

    // Create + resume the AudioContext SYNCHRONOUSLY inside the tap. iOS Safari only allows this
    // during the user gesture; after the getUserMedia await the gesture may no longer count.
    try {
      const AudioContextConstructor = window.AudioContext
        || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (AudioContextConstructor) {
        const context = new AudioContextConstructor();
        x.ctx = context;
        if (context.state === "suspended") void context.resume().catch(() => {});
      }
    } catch {
      x.ctx = null; // no Web Audio: manual stop + max cap still work
    }

    let stream: MediaStream;
    try {
      stream = await openMicrophone();
    } catch (caught) {
      fail(micErrorMessage(errorName(caught)));
      return;
    }
    if (unmounted.current) {
      stream.getTracks().forEach((track) => track.stop());
      releaseAudio();
      x.starting = false;
      return;
    }
    x.stream = stream;

    // Report the browser settings actually applied; do not assume constraints were honored.
    const track = stream.getAudioTracks()[0];
    const settings = track?.getSettings?.();
    setAudioFeatures(settings ? {
      echoCancellation: settings.echoCancellation,
      noiseSuppression: settings.noiseSuppression,
      autoGainControl: settings.autoGainControl,
    } : null);

    // MediaRecorder with a verified MIME type; fall back to the browser default if construction fails.
    const preferredMime = pickMimeType();
    let recorder: MediaRecorder | null = null;
    try {
      recorder = preferredMime ? new MediaRecorder(stream, { mimeType: preferredMime }) : new MediaRecorder(stream);
    } catch {
      try { recorder = new MediaRecorder(stream); } catch { recorder = null; }
    }
    if (!recorder) {
      fail("Could not start the recorder.");
      return;
    }
    const rec = recorder;
    x.recorder = rec;
    x.chunks = [];
    x.mime = rec.mimeType || preferredMime;
    x.stopping = false;
    x.discard = false;
    x.discardMessage = null;
    if (DEBUG) console.debug("[recorder] mime", { preferredMime, actual: rec.mimeType, track: settings });

    rec.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) x.chunks.push(event.data);
    };
    rec.onerror = () => fail("Recorder error. Please try again.");
    rec.onstop = async () => {
      const chunks = x.chunks;
      // A stop we did not request (track ended, OS took the mic) is an interruption: never submit it.
      const unexpected = !x.stopping;
      const discard = x.discard || unexpected;
      const message = x.discardMessage ?? (unexpected ? INTERRUPTED_MESSAGE : NO_SPEECH_MESSAGE);
      // Preserve the real container type the browser produced (webm on Android/desktop, mp4 on iOS).
      const mimeType = rec.mimeType || chunks.find((chunk) => chunk.type)?.type || x.mime || fallbackMime();
      releaseAudio();
      x.active = false;
      x.stopping = false;
      x.recorder = null;
      x.chunks = [];
      x.discard = false;
      x.discardMessage = null;
      if (unmounted.current) return;
      if (discard) {
        setError(message);
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

    // Web Audio level meter (never connected to speakers). Speech band-pass (100 Hz - 4 kHz) removes
    // rumble and hiss from the level measurement only; the recorded audio is untouched.
    let analyser: AnalyserNode | null = null;
    const context = x.ctx;
    if (context) {
      try {
        if (context.state !== "running") await resumeWithTimeout(context, 1000);
        const source = context.createMediaStreamSource(stream);
        const highpass = context.createBiquadFilter();
        highpass.type = "highpass";
        highpass.frequency.value = 100;
        const lowpass = context.createBiquadFilter();
        lowpass.type = "lowpass";
        lowpass.frequency.value = 4000;
        analyser = context.createAnalyser();
        analyser.fftSize = 2048; // ~43 ms window at 48 kHz: covers the whole 50 ms poll interval
        analyser.smoothingTimeConstant = 0;
        source.connect(highpass);
        highpass.connect(lowpass);
        lowpass.connect(analyser);
        x.source = source;
        x.nodes = [highpass, lowpass];
        x.analyser = analyser;
      } catch {
        analyser = null;
      }
    }
    setAutoStopAvailable(Boolean(analyser)); // false = manual stop + 60 s cap only (never cut the farmer off)

    if (unmounted.current) {
      x.recorder = null;
      releaseAudio();
      x.starting = false;
      return;
    }

    x.active = true;
    x.starting = false;

    // Mobile lifecycle: mic taken by a call/other app, or the page is backgrounded/locked.
    const onTrackEnded = () => abort(INTERRUPTED_MESSAGE);
    const onVisibility = () => { if (document.visibilityState === "hidden") abort(BACKGROUND_MESSAGE); };
    const onPageHide = () => abort(BACKGROUND_MESSAGE);
    track?.addEventListener("ended", onTrackEnded);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    x.cleanups.push(() => {
      track?.removeEventListener("ended", onTrackEnded);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
    });

    try {
      rec.start(250);
      setState("listening");
    } catch {
      fail("Could not start the recorder.");
      return;
    }

    const startedAt = performance.now();
    const silenceMs = silenceRef.current;
    const activeAnalyser = analyser;
    const buffer = new Float32Array(activeAnalyser?.fftSize ?? 2048);

    let previousAt = startedAt;
    let manualOnly = !activeAnalyser;
    let calibrated = false;
    const calibration: number[] = [];
    const recent: number[] = [];
    let noiseFloor = 0.008;
    let speechRef = 0;          // running level of the farmer's own speech (for relative gating)
    let speechDetected = false;
    let startMs = 0;            // sustained voiced time before speech is confirmed
    let extendMs = 0;           // sustained sound time that may extend an ongoing recording
    let lastVoiceAt = startedAt;
    let blockedMs = 0;
    let zeroMs = 0;
    let sawSignal = false;
    let lastResumeTry = 0;
    let ticks = 0;
    let uiState: RecState = "listening";
    const show = (next: RecState) => {
      if (next !== uiState) {
        uiState = next;
        setState(next);
      }
    };
    const goManual = () => {
      manualOnly = true;
      setAutoStopAvailable(false);
      show("listening");
    };

    x.timer = setInterval(() => {
      if (!x.active || x.stopping) return;
      const now = performance.now();
      const delta = now - previousAt;
      previousAt = now;
      const elapsed = now - startedAt;

      if (elapsed >= MAX_RECORDING_MS) return finish("max");
      if (manualOnly || !activeAnalyser) return;

      // Suspended/interrupted AudioContext returns zeros: never mistake that for "no speech".
      const ctxNow = x.ctx;
      if (ctxNow && ctxNow.state !== "running") {
        blockedMs += delta;
        if (now - lastResumeTry > 500) {
          lastResumeTry = now;
          ctxNow.resume().catch(() => {});
        }
        if (blockedMs >= ANALYSIS_BLOCKED_MS) goManual();
        return;
      }
      blockedMs = 0;

      activeAnalyser.getFloatTimeDomainData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
      const rms = Math.sqrt(sum / buffer.length);

      // An analyser that never produces a non-zero sample is dead (some browsers): go manual.
      if (rms > 0) {
        sawSignal = true;
        zeroMs = 0;
      } else if (!sawSignal) {
        zeroMs += delta;
        if (zeroMs >= DEAD_ANALYSER_MS) return goManual();
      }

      // Transient-spike rejection: the median of the last ~250 ms ignores 1-2 frame bursts (claps, taps).
      recent.push(rms);
      if (recent.length > MEDIAN_WINDOW) recent.shift();
      const level = median(recent);

      if (!calibrated) {
        calibration.push(rms);
        if (elapsed < CALIBRATION_MS) return;
        const sorted = [...calibration].sort((a, b) => a - b);
        // 20th percentile: robust if the farmer starts talking during calibration.
        noiseFloor = Math.min(NOISE_FLOOR_MAX, sorted[Math.floor(sorted.length * 0.2)]);
        calibrated = true;
      }

      // Slow adaptive noise floor: falls quickly, rises only for sound barely above the floor.
      if (level < noiseFloor) {
        noiseFloor += (level - noiseFloor) * 0.2;
      } else if (level < Math.max(END_MIN, noiseFloor * END_RATIO)) {
        noiseFloor = Math.min(NOISE_FLOOR_MAX, noiseFloor + (level - noiseFloor) * 0.01);
      }

      // Hysteresis: higher threshold to start speech, lower to keep it alive.
      const startThr = Math.max(START_MIN, noiseFloor * START_RATIO);
      const endThr = Math.max(
        END_MIN,
        noiseFloor * END_RATIO,
        Math.min(END_MAX, speechRef * RELATIVE_END_RATIO),
      );

      if (DEBUG && ++ticks % 10 === 0) {
        console.debug("[recorder]", {
          rms: +rms.toFixed(4), level: +level.toFixed(4), floor: +noiseFloor.toFixed(4),
          startThr: +startThr.toFixed(4), endThr: +endThr.toFixed(4), speechRef: +speechRef.toFixed(4),
          speech: speechDetected, silentMs: Math.round(now - lastVoiceAt),
        });
      }

      if (!speechDetected) {
        startMs = level >= startThr ? startMs + delta : Math.max(0, startMs - 2 * delta);
        if (startMs >= MIN_SPEECH_MS) {
          speechDetected = true;
          lastVoiceAt = now;
          speechRef = Math.max(level, startThr);
          show("speech");
        } else if (elapsed > NO_SPEECH_TIMEOUT_MS) {
          finish("no_speech");
        }
        return;
      }

      if (level >= endThr) {
        extendMs += delta;
        if (level >= startThr) speechRef += (level - speechRef) * 0.05;
        // Only SUSTAINED sound resets the silence timer; a clap never reaches this.
        if (extendMs >= EXTEND_CONFIRM_MS) {
          lastVoiceAt = now;
          show("speech");
        }
      } else {
        extendMs = 0; // hard reset: an isolated spike cannot ride on earlier accumulated time
        const silentFor = now - lastVoiceAt;
        if (silentFor >= silenceMs) finish("silence");
        else if (silentFor >= SHOW_FINISHING_AFTER_MS) show("finishing");
      }
    }, POLL_MS);
  }, [abort, fail, finish, releaseAudio]);

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