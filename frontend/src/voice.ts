// Voice engine for Neura: browser speech-to-text (so you can speak) and CHUNKED
// Kokoro text-to-speech (so playback starts on the first sentence and keeps going
// for long answers). Both expose a live AnalyserNode so the blob orb can pulse.

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

export interface Speaker {
  stop(): void;
}

// TTS speaks with a US English Kokoro voice by default (af_* are American English).
export const US_VOICE = "af_heart";

/** Normalise text into clean, readable speech — no markdown, symbols, code, URLs,
 *  emoji, list markers, or source citations. */
export function cleanForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ") // code blocks
    .replace(/`[^`]*`/g, " ") // inline code
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ") // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // links → label
    .replace(/https?:\/\/\S+/g, " ") // bare URLs
    .replace(/\((?:from |source:|GLOBAL|LOCAL|match\s)[^)]*\)/gi, " ") // citations
    .replace(/^\s*(?:[-*•]|\d+[.)])\s+/gm, "") // list markers
    .replace(/^\s{0,3}#{1,6}\s+/gm, "") // headings
    .replace(/[*_~>#|]/g, "") // stray markdown symbols
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2190}-\u{21FF}\u{2B00}-\u{2BFF}\u{FE0F}]/gu, "") // emoji
    .replace(/\n+/g, ". ") // line breaks → sentence breaks
    .replace(/\.\s*(?:\.\s*)+/g, ". ") // collapse repeated periods
    .replace(/\s+([.,!?;:])/g, "$1") // no space before punctuation
    .replace(/\s+/g, " ")
    .trim();
}

/** Split text into speakable chunks (~sentence groups) so the first can play fast. */
export function chunkText(text: string, target = 200): string[] {
  const clean = cleanForSpeech(text);
  if (!clean) return [];
  const sentences = clean.match(/[^.!?\n]+[.!?]?/g) || [clean];
  const chunks: string[] = [];
  let buf = "";
  for (const s of sentences) {
    const seg = s.trim();
    if (!seg) continue;
    if ((buf + " " + seg).trim().length > target && buf) {
      chunks.push(buf.trim());
      buf = seg;
    } else {
      buf = (buf + " " + seg).trim();
    }
  }
  if (buf.trim()) chunks.push(buf.trim());
  return chunks;
}

interface SpeakOpts {
  voice?: string;
  onState?(s: OrbState): void;
  onAnalyser?(a: AnalyserNode | null): void;
  onDone?(): void;
}

/** Speak `text` via Kokoro, one chunk at a time, prefetching the next while the
 *  current one plays. Returns a controller whose stop() halts everything. */
export function speak(text: string, opts: SpeakOpts = {}): Speaker {
  const chunks = chunkText(text);
  if (!chunks.length) {
    opts.onState?.("idle");
    opts.onDone?.();
    return { stop() {} };
  }
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  analyser.connect(ctx.destination);
  opts.onAnalyser?.(analyser);

  let stopped = false;
  const controllers: AbortController[] = [];

  async function fetchBuf(i: number): Promise<AudioBuffer | null> {
    const ac = new AbortController();
    controllers.push(ac);
    try {
      const r = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: chunks[i], voice: opts.voice || US_VOICE, speed: 1.0 }),
        signal: ac.signal,
      });
      if (!r.ok) return null;
      const arr = await r.arrayBuffer();
      return await ctx.decodeAudioData(arr);
    } catch {
      return null;
    }
  }

  function play(buf: AudioBuffer): Promise<void> {
    return new Promise((res) => {
      if (stopped) return res();
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(analyser);
      src.onended = () => res();
      try {
        src.start();
      } catch {
        res();
      }
    });
  }

  (async () => {
    try {
      let next = fetchBuf(0);
      for (let i = 0; i < chunks.length && !stopped; i++) {
        const buf = await next;
        if (i + 1 < chunks.length) next = fetchBuf(i + 1);
        if (stopped || !buf) {
          if (!buf) continue;
        }
        if (i === 0) opts.onState?.("speaking");
        if (buf) await play(buf);
      }
    } finally {
      try {
        ctx.close();
      } catch {
        /* ignore */
      }
      opts.onAnalyser?.(null);
      if (!stopped) {
        opts.onState?.("idle");
        opts.onDone?.();
      }
    }
  })();

  return {
    stop() {
      stopped = true;
      controllers.forEach((c) => c.abort());
      try {
        ctx.close();
      } catch {
        /* ignore */
      }
      opts.onAnalyser?.(null);
      opts.onState?.("idle");
    },
  };
}

export interface StreamSpeaker {
  push(fullText: string): void; // feed the growing answer; complete sentences get spoken
  end(): void; // no more text — flush the remainder
  stop(): void;
}

/** Speak an answer WHILE it streams in: as each sentence completes it's queued to
 *  Kokoro, so the voice starts replying within a sentence instead of after the
 *  whole (possibly long) answer is generated. */
export function speakStream(opts: SpeakOpts = {}): StreamSpeaker {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  analyser.connect(ctx.destination);
  opts.onAnalyser?.(analyser);

  const queue: string[] = [];
  const controllers: AbortController[] = [];
  let spokenLen = 0;
  let lastFull = "";
  let stopped = false;
  let ended = false;
  let pumping = false;
  let started = false;

  async function synth(text: string): Promise<AudioBuffer | null> {
    const ac = new AbortController();
    controllers.push(ac);
    try {
      const r = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: opts.voice || US_VOICE, speed: 1.0 }),
        signal: ac.signal,
      });
      if (!r.ok) return null;
      return await ctx.decodeAudioData(await r.arrayBuffer());
    } catch {
      return null;
    }
  }
  function play(buf: AudioBuffer): Promise<void> {
    return new Promise((res) => {
      if (stopped) return res();
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(analyser);
      src.onended = () => res();
      try {
        src.start();
      } catch {
        res();
      }
    });
  }
  function finish() {
    try {
      ctx.close();
    } catch {
      /* ignore */
    }
    opts.onAnalyser?.(null);
    if (!stopped) {
      opts.onState?.("idle");
      opts.onDone?.();
    }
  }
  async function pump() {
    if (pumping) return;
    pumping = true;
    while (queue.length && !stopped) {
      const text = queue.shift()!;
      const buf = await synth(text);
      if (stopped) break;
      if (!buf) continue;
      if (!started) {
        started = true;
        opts.onState?.("speaking");
      }
      await play(buf);
    }
    pumping = false;
    if (ended && !queue.length && !stopped) finish();
  }
  function enqueue(raw: string) {
    const c = cleanForSpeech(raw);
    if (c) {
      queue.push(c);
      pump();
    }
  }

  return {
    push(full: string) {
      if (stopped) return;
      lastFull = full;
      const pending = full.slice(spokenLen);
      const re = /[^.!?\n]*[.!?\n]+/g;
      let m: RegExpExecArray | null;
      let consumed = 0;
      const sentences: string[] = [];
      while ((m = re.exec(pending)) !== null) {
        sentences.push(m[0]);
        consumed = m.index + m[0].length;
      }
      if (consumed > 0) {
        spokenLen += consumed;
        sentences.forEach(enqueue);
      }
    },
    end() {
      ended = true;
      const rest = lastFull.slice(spokenLen);
      spokenLen = lastFull.length;
      enqueue(rest);
      if (!pumping && !queue.length) finish();
      else pump();
    },
    stop() {
      stopped = true;
      controllers.forEach((c) => c.abort());
      try {
        ctx.close();
      } catch {
        /* ignore */
      }
      opts.onAnalyser?.(null);
      opts.onState?.("idle");
    },
  };
}

interface ListenOpts {
  onState?(s: OrbState): void;
  onAnalyser?(a: AnalyserNode | null): void;
  onPartial?(text: string): void;
  onFinal?(text: string): void;
  onUnsupported?(): void;
}

export function speechSupported(): boolean {
  return !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

/** Listen to the mic (Web Speech API) and stream a transcript; the mic also feeds
 *  an AnalyserNode so the orb reacts while you talk. */
export function listen(opts: ListenOpts = {}): Speaker {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SR) {
    opts.onUnsupported?.();
    opts.onState?.("idle");
    return { stop() {} };
  }
  let stream: MediaStream | null = null;
  let actx: AudioContext | null = null;
  let finalText = "";
  let done = false;

  const recog = new SR();
  recog.lang = "en-IN"; // recognise Indian-accented English
  recog.interimResults = true;
  recog.continuous = false;

  opts.onState?.("listening");
  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then((s) => {
      stream = s;
      actx = new AudioContext();
      const src = actx.createMediaStreamSource(s);
      const an = actx.createAnalyser();
      an.fftSize = 256;
      src.connect(an);
      opts.onAnalyser?.(an);
    })
    .catch(() => {});

  const cleanup = () => {
    stream?.getTracks().forEach((t) => t.stop());
    try {
      actx?.close();
    } catch {
      /* ignore */
    }
    opts.onAnalyser?.(null);
  };

  recog.onresult = (e: any) => {
    let t = "";
    for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
    finalText = t;
    opts.onPartial?.(t.trim());
  };
  recog.onerror = () => {};
  recog.onend = () => {
    if (done) return;
    done = true;
    cleanup();
    const t = finalText.trim();
    if (t) opts.onFinal?.(t);
    else opts.onState?.("idle");
  };

  try {
    recog.start();
  } catch {
    /* already started */
  }

  return {
    stop() {
      done = true;
      try {
        recog.abort();
      } catch {
        /* ignore */
      }
      cleanup();
      opts.onState?.("idle");
    },
  };
}
