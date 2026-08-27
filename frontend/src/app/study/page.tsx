"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import FlashcardView from "@/components/FlashcardView";
import ListenView from "@/components/ListenView";
import QuizView from "@/components/QuizView";

function StudyContent() {
  const params = useSearchParams();
  const view = params.get("view") ?? "read";
  const segments = [
    { key: "read", label: "看背" },
    { key: "listen", label: "听学" },
    { key: "quiz", label: "自测" },
  ];
  return (
    <div className="page-box">
      <div className="segments">
        {segments.map((s) => (
          <button
            key={s.key}
            className={`segment${view === s.key ? " active" : ""}`}
            onClick={() => { window.location.href = `/study?view=${s.key}`; }}
          >
            {s.label}
          </button>
        ))}
      </div>
      {view === "read" && <FlashcardView />}
      {view === "listen" && <ListenView />}
      {view === "quiz" && <QuizView />}
    </div>
  );
}

export default function StudyPage() {
  return (
    <Suspense fallback={<p className="muted">加载中…</p>}>
      <StudyContent />
    </Suspense>
  );
}
