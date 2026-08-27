"use client";
import { useEffect, useState } from "react";
import { getJson, putJson } from "@/lib/api";

interface Settings {
  exam_date: string;
  capacity_max: number;
  deepseek_configured: boolean;
  days_left: number | null;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [examDate, setExamDate] = useState("");
  const [capMax, setCapMax] = useState(50);
  const [message, setMessage] = useState("");
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    getJson<Settings>("/api/settings").then((s) => {
      setSettings(s);
      setExamDate(s.exam_date || "");
      setCapMax(s.capacity_max);
    });
  }, []);

  async function save() {
    try {
      const s = await putJson<Settings>("/api/settings", {
        exam_date: examDate || null,
        capacity_max: capMax,
      });
      setSettings(s);
      setMessage("已保存");
    } catch (e) {
      setMessage("保存失败：" + String(e));
    }
  }

  async function doImport(file: File) {
    setImporting(true);
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/import", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) {
        setMessage("导入失败：" + JSON.stringify(data.detail ?? data));
      } else {
        setMessage(`导入成功：${data.imported} 条`);
      }
    } catch (e) {
      setMessage("导入失败：" + String(e));
    } finally {
      setImporting(false);
    }
  }

  if (!settings) return <p className="muted">加载中…</p>;
  return (
    <div className="page-box">
      <header className="page-head"><h1>我的</h1></header>

      <section className="card">
        <h2 className="card-title">备考设置</h2>
        <label className="field">
          考试日期
          <input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} />
        </label>
        <label className="field">
          每日上限（5–200）
          <input type="number" min={5} max={200} value={capMax}
            onChange={(e) => setCapMax(Number(e.target.value))} />
        </label>
        <button className="btn btn-primary" onClick={() => void save()}>保存</button>
        {settings.days_left !== null && <p className="muted">距考试 {settings.days_left} 天</p>}
        {message && <p className="muted">{message}</p>}
      </section>

      <section className="card">
        <h2 className="card-title">DeepSeek</h2>
        <p className={settings.deepseek_configured ? "ok" : "bad"}>
          {settings.deepseek_configured
            ? "已配置（key 在服务器 .env）"
            : "未配置：在服务器 .env 填入 DEEPSEEK_API_KEY 后重启后端"}
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">数据导入</h2>
        <input
          type="file"
          accept=".json"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void doImport(f);
          }}
        />
        {importing && <p className="muted">导入中…</p>}
      </section>
    </div>
  );
}
