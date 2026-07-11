import { useEffect, useRef, useState } from "react";
import VoiceOrb from "./VoiceOrb";
import { listen, speak, speechSupported, type OrbState, type Speaker } from "../voice";
import { Mic, Stop, Close } from "../icons";

interface Props {
  open: boolean;
  onClose(): void;
  // Send the spoken text through the normal chat pipeline; resolves to the
  // final answer text so we can speak it back.
  onSend(text: string): Promise<string>;
}

const LABEL: Record<OrbState, string> = {
  idle: "Tap the mic to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

export default function VoiceOverlay({ open, onClose, onSend }: Props) {
  const [state, setState] = useState<OrbState>("idle");
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [transcript, setTranscript] = useState("");
  const listenRef = useRef<Speaker | null>(null);
  const speakRef = useRef<Speaker | null>(null);

  function stopAll() {
    listenRef.current?.stop();
    listenRef.current = null;
    speakRef.current?.stop();
    speakRef.current = null;
    setState("idle");
    setAnalyser(null);
  }

  async function startTurn() {
    stopAll();
    setTranscript("");
    if (!speechSupported()) {
      setTranscript("Speech input needs Chrome or Edge. You can still type below.");
      return;
    }
    listenRef.current = listen({
      onState: setState,
      onAnalyser: setAnalyser,
      onPartial: setTranscript,
      onFinal: async (text) => {
        listenRef.current = null;
        setTranscript(text);
        setState("thinking");
        setAnalyser(null);
        let answer = "";
        try {
          answer = await onSend(text);
        } catch {
          /* ignore */
        }
        if (answer) {
          speakRef.current = speak(answer, { onState: setState, onAnalyser: setAnalyser });
        } else {
          setState("idle");
        }
      },
    });
  }

  // Start a listening turn automatically when the overlay opens; tidy up on close.
  useEffect(() => {
    if (open) startTurn();
    else stopAll();
    return () => stopAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const busy = state === "listening" || state === "thinking" || state === "speaking";

  return (
    <div className="voice-scrim" onClick={onClose}>
      <div className="voice-panel" onClick={(e) => e.stopPropagation()}>
        <button className="voice-x" onClick={onClose} title="Close voice mode">
          <Close />
        </button>
        <div className="voice-orb-wrap">
          <VoiceOrb state={state} analyser={analyser} size={240} />
        </div>
        <div className={"voice-label s-" + state}>{LABEL[state]}</div>
        {transcript && <div className="voice-transcript">{transcript}</div>}
        <div className="voice-actions">
          {busy ? (
            <button className="voice-btn stop" onClick={stopAll}>
              <Stop /> Stop
            </button>
          ) : (
            <button className="voice-btn mic" onClick={startTurn}>
              <Mic /> Speak
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
