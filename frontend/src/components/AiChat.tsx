"use client";
import { useEffect, useRef, useState } from "react";
import { mdToHtml } from "@/lib/md";
import { getJson } from "@/lib/api";
import type { AiPrefill } from "./AiFab";

interface Msg { role: "user" | "ai"; text: string; }
interface HistoryItem {
  id: number;
  ts: string;
  question: string;
  answer: string;
  related_entry_ids: string[];
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fallback 见下 */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  } catch {
    return false;
  }
}

export default function AiChat({
  open, onClose, prefill,
}: {
  open: boolean;
  onClose: () => void;
  prefill: AiPrefill | null;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [tip, setTip] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const entryId = prefill?.entry_id ?? "";

  useEffect(() => {
    if (prefill) {
      setInput(prefill.question);
      setMessages([]);
      setShowHistory(false);
      setTip("");
      if (prefill.title || prefill.description) {
        setTitle(prefill.title ?? "");
        setDescription(prefill.description ?? "");
      } else if (prefill.entry_id) {
        setTitle("");
        setDescription("");
        getJson<{ id: string; point: string; anchor: string; conclusion: string }>(
          `/api/entries/${encodeURIComponent(prefill.entry_id)}`
        ).then((e) => {
          setTitle(e.point ?? "");
          setDescription(`场景：${e.anchor ?? ""}\n结论：${e.conclusion ?? ""}`);
        }).catch(() => {});
      } else {
        setTitle("");
        setDescription("");
      }
    }
  }, [prefill]);

  useEffect(() => {
    if (!open || !entryId) {
      if (!entryId) setHistory([]);
      return;
    }
    getJson<{ items: HistoryItem[] }>(
      `/api/assistant/history?entry_id=${encodeURIComponent(entryId)}&limit=20`
    ).then((d) => setHistory(d.items)).catch(() => {});
  }, [open, entryId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, open]);

  function refreshHistory() {
    if (!entryId) return;
    getJson<{ items: HistoryItem[] }>(
      `/api/assistant/history?entry_id=${encodeURIComponent(entryId)}&limit=20`
    ).then((d) => setHistory(d.items)).catch(() => {});
  }

  function appendToInput(text: string) {
    if (!text) return;
    setInput((prev) => (prev ? `${prev}\n${text}` : text));
  }

  async function handleCopy(text: string, label: string) {
    if (!text) return;
    setTip((await copyText(text)) ? `已复制${label}` : "复制失败，请长按手动复制");
  }

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "ai", text: "" }]);
    let gotAnswer = false;
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
          if (payload.delta) gotAnswer = true;
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
      refreshHistory();
      if (gotAnswer && prefill?.entry_id) {
        window.dispatchEvent(new CustomEvent("ai-asked", {
          detail: { entry_id: prefill.entry_id },
        }));
      }
    }
  }

  if (!open) return null;
  return (
    <div className="ai-chat">
      <div className="ai-chat-head">
        <b>AI 助手</b>
        <button onClick={onClose}>×</button>
      </div>
      {(title || description) && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "8px 12px 0" }}>
          {title && (
            <>
              <button className="badge-btn" onClick={() => appendToInput(title)}>标题→输入</button>
              <button className="badge-btn" onClick={() => void handleCopy(title, "标题")}>复制标题</button>
            </>
          )}
          {description && (
            <>
              <button className="badge-btn" onClick={() => appendToInput(description)}>描述→输入</button>
              <button className="badge-btn" onClick={() => void handleCopy(description, "描述")}>复制描述</button>
            </>
          )}
          {tip && <span className="muted" style={{ fontSize: 12 }}>{tip}</span>}
        </div>
      )}
      {entryId && history.length > 0 && (
        <div style={{ padding: "8px 12px 0" }}>
          <button className="badge-btn" onClick={() => setShowHistory((s) => !s)}>
            {showHistory ? "收起历史问答" : `历史问答（${history.length}）`}
          </button>
          {showHistory && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
              {history.map((h) => (
                <div key={h.id} className="analysis" style={{ marginTop: 0 }}>
                  <p className="muted" style={{ fontSize: 12 }}>{h.ts.slice(0, 16).replace("T", " ")}</p>
                  <p style={{ fontWeight: 600 }}>问：{h.question}</p>
                  <p className="muted">答：{h.answer.slice(0, 120)}{h.answer.length > 120 ? "…" : ""}</p>
                  <button className="badge-btn" onClick={() => { setInput(h.question); setShowHistory(false); }}>
                    回填这个问题
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
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
