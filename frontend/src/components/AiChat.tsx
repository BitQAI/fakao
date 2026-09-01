"use client";
import { useEffect, useRef, useState } from "react";
import { mdToHtml } from "@/lib/md";

interface Msg { role: "user" | "ai"; text: string; }

export default function AiChat({
  open, onClose, prefill,
}: {
  open: boolean;
  onClose: () => void;
  prefill: { question: string; entry_id?: string } | null;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (prefill) {
      setInput(prefill.question);
      setMessages([]);
    }
  }, [prefill]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, open]);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "ai", text: "" }]);
    try {
      const res = await fetch("/api/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          entry_id: prefill?.entry_id ?? undefined,
        }),
      });
      if (!res.body) throw new Error("无响应流");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = JSON.parse(line.slice(6));
          setMessages((m) => {
            const next = [...m];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, text: last.text + payload.delta };
            return next;
          });
        }
      }
    } catch (e) {
      setMessages((m) => [
        ...m.slice(0, -1),
        { role: "ai", text: "连接失败：" + String(e) },
      ]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  return (
    <div className="ai-chat">
      <div className="ai-chat-head">
        <b>AI 助手</b>
        <button onClick={onClose}>×</button>
      </div>
      <div className="ai-chat-body">
        {messages.length === 0 && <p className="muted">随时提问，答案会引用条目出处。</p>}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            {m.role === "ai" ? (
              <div
                className="chat-bubble"
                dangerouslySetInnerHTML={{ __html: mdToHtml(m.text || "…") }}
              />
            ) : (
              <div className="chat-bubble">{m.text || "…"}</div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <form
        className="ai-chat-input"
        onSubmit={(e) => { e.preventDefault(); void ask(input); }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入问题…"
          disabled={busy}
        />
        <button type="submit" disabled={busy}>发送</button>
      </form>
    </div>
  );
}
