"use client";
import { useEffect, useState } from "react";
import AiChat from "./AiChat";

export default function AiFab() {
  const [open, setOpen] = useState(false);
  const [prefill, setPrefill] = useState<{ question: string; entry_id?: string } | null>(null);

  useEffect(() => {
    function handler(e: Event) {
      const detail = (e as CustomEvent<{ question: string; entry_id?: string }>).detail;
      setPrefill(detail);
      setOpen(true);
    }
    window.addEventListener("ask-ai", handler);
    return () => window.removeEventListener("ask-ai", handler);
  }, []);

  return (
    <>
      <button className="ai-fab" onClick={() => setOpen((o) => !o)}>AI</button>
      <AiChat open={open} onClose={() => setOpen(false)} prefill={prefill} />
    </>
  );
}
