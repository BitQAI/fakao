"use client";
import { useEffect, useState } from "react";
import AiChat from "./AiChat";
import { IconAi } from "./icons";

export interface AiPrefill {
  question: string;
  entry_id?: string;
  title?: string;
  description?: string;
}

export default function AiFab() {
  const [open, setOpen] = useState(false);
  const [prefill, setPrefill] = useState<AiPrefill | null>(null);

  useEffect(() => {
    function handler(e: Event) {
      const detail = (e as CustomEvent<AiPrefill>).detail;
      setPrefill(detail);
      setOpen(true);
    }
    window.addEventListener("ask-ai", handler);
    return () => window.removeEventListener("ask-ai", handler);
  }, []);

  return (
    <>
      <button className="ai-fab" onClick={() => setOpen((o) => !o)} aria-label="AI 助手">
        <IconAi />
      </button>
      <AiChat open={open} onClose={() => setOpen(false)} prefill={prefill} />
    </>
  );
}
