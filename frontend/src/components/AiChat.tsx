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
  // 默认全部展开（与对话区一致的完整渲染）；用户可逐条收起，collapsedIds 记录被收起的 id
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set());
  const [tip, setTip] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const entryId = prefill?.entry_id ?? "";
  const MAX_INPUT_H = 132;

  function stopStream() {
    abortRef.current?.abort();
    abortRef.current = null;
  }

  function autosize() {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    const h = Math.min(el.scrollHeight, MAX_INPUT_H);
    el.style.height = `${h}px`;
    el.style.overflowY = el.scrollHeight > MAX_INPUT_H ? "auto" : "hidden";
  }

  useEffect(() => {
    autosize();
  }, [input, open]);

  useEffect(() => {
    if (open) {
      // 面板弹出后重置高度并聚焦（桌面端直接聚焦，移动端避免强制弹键盘则仅重置）
      autosize();
      const t = window.setTimeout(() => {
        if (window.matchMedia?.("(pointer: fine)").matches) taRef.current?.focus();
      }, 60);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      // 关闭面板即结束本轮会话：中断流式输出并清空对话，
      // 下次打开（即使已切到新题）不再残留上题内容
      stopStream();
      setMessages([]);
    }
  }, [open]);

  useEffect(() => {
    if (prefill) {
      // 切到新题：中断上一题未完成的流式输出（防止旧内容续写进新会话），清空输入与对话
      stopStream();
      setInput("");
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

  function toggleCollapsed(id: number) {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function appendToInput(text: string) {
    if (!text) return;
    setInput((prev) => (prev ? `${prev}\n${text}` : text));
    requestAnimationFrame(() => {
      autosize();
      taRef.current?.focus();
    });
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
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let gotAnswer = false;
    try {
      const res = await fetch("/api/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          entry_id: prefill?.entry_id ?? undefined,
        }),
        signal: ctrl.signal,
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
      // 切题/关面板导致的中断：静默丢弃，不写错误气泡、不污染新会话
      if (ctrl.signal.aborted) return;
      setMessages((m) => [
        ...m.slice(0, -1),
        { role: "ai", text: "连接失败：" + String(e) },
      ]);
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      if (ctrl.signal.aborted) {
        setBusy(false);
        return;
      }
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
  const canSend = !busy && input.trim().length > 0;
  const suggestions = entryId
    ? ["一句话讲清这个考点", "举一个真题例子", "有哪些易混淆点？"]
    : ["今天先背哪 20 条最高效？", "商经公司法怎么记？", "刑法因果关系怎么判断？"];
  return (
    <div className="ai-chat">
      <div className="ai-chat-head">
        <div className="ai-head-info">
          <span className="ai-dot" />
          <div className="ai-head-text">
            <b>AI 助手</b>
            <span>结合条目出处作答</span>
          </div>
        </div>
        <button onClick={onClose} aria-label="关闭">×</button>
      </div>
      {(title || description) ? (
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
      ) : (
        <div style={{ padding: "8px 12px 0" }}>
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            从看背卡片点「问 AI」，可带标题 / 描述快捷填入与历史问答。
            {tip && ` · ${tip}`}
          </p>
        </div>
      )}
      {entryId && history.length > 0 && (
        <div style={{ padding: "8px 12px 0" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button className="badge-btn" onClick={() => setShowHistory((s) => !s)}>
              {showHistory ? "收起历史问答" : `历史问答（${history.length}）`}
            </button>
            {showHistory && (
              collapsedIds.size >= history.length ? (
                <button className="badge-btn" onClick={() => setCollapsedIds(new Set())}>
                  全部展开
                </button>
              ) : (
                <button className="badge-btn" onClick={() => setCollapsedIds(new Set(history.map((h) => h.id)))}>
                  全部收起
                </button>
              )
            )}
          </div>
          {showHistory && (
            <div className="ai-history-list">
              {history.map((h) => {
                const collapsed = collapsedIds.has(h.id);
                const preview = h.answer.replace(/\s+/g, " ").slice(0, 120);
                return (
                  <div key={h.id} className="ai-history-item">
                    <p className="muted" style={{ fontSize: 12, margin: 0 }}>{h.ts.slice(0, 16).replace("T", " ")}</p>
                    {/* 提问：与对话区用户气泡同款 */}
                    <div className="chat-msg user" style={{ flexDirection: "column", alignItems: "flex-end" }}>
                      <div className="chat-bubble">{h.question}</div>
                    </div>
                    {collapsed ? (
                      <p className="muted ai-history-preview">
                        答：{preview}{h.answer.length > 120 ? "…" : ""}
                      </p>
                    ) : (
                      <>
                        {/* 回答：与对话区 AI 气泡同款 Markdown 渲染 */}
                        <div className="chat-msg ai" style={{ flexDirection: "column", alignItems: "flex-start" }}>
                          <div
                            className="chat-bubble ai-md"
                            style={{ maxWidth: "100%" }}
                            dangerouslySetInnerHTML={{ __html: mdToHtml(h.answer) }}
                          />
                          <button className="badge-btn" style={{ marginTop: 4 }} onClick={() => void handleCopy(h.answer, "回答")}>
                            复制回答
                          </button>
                        </div>
                        {h.related_entry_ids?.length > 0 && (
                          <p className="muted" style={{ fontSize: 11, margin: 0 }}>
                            引用条目：{h.related_entry_ids.join(" · ")}
                          </p>
                        )}
                      </>
                    )}
                    <div className="ai-history-actions">
                      <button className="badge-btn" onClick={() => toggleCollapsed(h.id)}>
                        {collapsed ? "展开全文" : "收起全文"}
                      </button>
                      <button className="badge-btn" onClick={() => { setInput(h.question); setShowHistory(false); requestAnimationFrame(() => { autosize(); taRef.current?.focus(); }); }}>
                        回填这个问题
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
      <div className="ai-chat-body">
        {messages.length === 0 && (
          <div className="ai-empty">
            <div className="ai-empty-icon">✦</div>
            <p>随时提问，答案会引用条目出处。</p>
            <div className="ai-suggests">
              {suggestions.map((s) => (
                <button
                  key={s}
                  className="ai-suggest"
                  disabled={busy}
                  onClick={() => void ask(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`} style={{ flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start" }}>
            {m.role === "ai" ? (
              <>
                {m.text ? (
                  <div
                    className={`chat-bubble ai-md${busy && i === messages.length - 1 ? " streaming" : ""}`}
                    style={{ maxWidth: "100%" }}
                    dangerouslySetInnerHTML={{ __html: mdToHtml(m.text) }}
                  />
                ) : (
                  <div className="chat-bubble ai-typing" style={{ maxWidth: "100%" }}>
                    <span /><span /><span />
                  </div>
                )}
                {m.text && (
                  <button className="badge-btn" style={{ marginTop: 4 }} onClick={() => void handleCopy(m.text, "回答")}>
                    复制回答
                  </button>
                )}
              </>
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
        <div className="ai-composer">
          <textarea
            ref={taRef}
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void ask(input);
              }
            }}
            placeholder="输入问题，Enter 发送…"
            disabled={busy}
            aria-label="输入问题"
          />
          <button type="submit" className="ai-send" disabled={!canSend} aria-label="发送">
            {busy ? <span className="ai-spinner" /> : <span className="ai-arrow">↑</span>}
          </button>
        </div>
        <div className="ai-input-meta">
          <span>Enter 发送 · Shift+Enter 换行</span>
          {input.length > 0 && <span>{input.length} 字</span>}
        </div>
      </form>
    </div>
  );
}
