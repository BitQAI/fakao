"use client";
import type { ReactNode } from "react";

interface Props {
  /** true=空队列（还没内容），false=本轮听完了 */
  empty: boolean;
  custom: boolean;
  itemsCount: number;
  remaining: number;
  /** 已听过的段数（空队列时不显示） */
  queueRemaining: number;
  loadingMore: boolean;
  moreCount: string;
  notice: string;
  hasRange: boolean;
  onCountChange: (value: string) => void;
  onPickRange: () => void;
  onClearRange: () => void;
  onContinueRange: (limit: number) => void;
  onLoadMore: (count: number) => void;
  /** 空队列时卡片内的补充内容（按钮等） */
  children?: ReactNode;
}

/** 听学的空队列提示与本轮完成卡片（模式与看背的 ReadFinishCard 对齐）。 */
export default function ListenFinishCard({
  empty, custom, itemsCount, remaining, queueRemaining, loadingMore,
  moreCount, notice, hasRange, onCountChange, onPickRange, onClearRange,
  onContinueRange, onLoadMore,
  children,
}: Props) {
  const count = Number(moreCount);
  if (empty) {
    return (
      <div className="card">
        <p>{queueRemaining === 0 ? "暂无听学内容。" : "正在生成更多听学内容…"}</p>
        {queueRemaining === 0 && <p className="muted">剩余不足时系统会自动续批生成。</p>}
        {notice && <p className="muted">{notice}</p>}
        {children}
      </div>
    );
  }
  return (
    <div className="card center">
      <h2>{custom ? "自定义范围已学完" : "本轮听学完成"}</h2>
      <p className="muted">共听了 {itemsCount} 段 · 剩余可听 {queueRemaining}</p>
      {custom ? (
        <div>
          <div className="row">
            <button className="btn btn-primary"
              onClick={() => { onClearRange(); onPickRange(); }}>重新选择范围</button>
          </div>
          {hasRange && remaining > 0 ? (
            <div className="continue-box">
              <p className="muted">剩余未听 {remaining} 段，选择下一组或部分：</p>
              <div className="row">
                <button className="btn" disabled={loadingMore}
                  onClick={() => onContinueRange(20)}>下一组 20</button>
                <button className="btn" disabled={loadingMore}
                  onClick={() => onContinueRange(50)}>下一组 50</button>
              </div>
              <div className="continue-custom">
                <input type="number" min={1} max={50} placeholder="自定义数量"
                  value={moreCount} onChange={(e) => onCountChange(e.target.value)} />
                <button className="btn btn-primary" disabled={loadingMore || !count}
                  onClick={() => onContinueRange(count)}>继续</button>
              </div>
              {notice && <p className="muted">{notice}</p>}
            </div>
          ) : <p className="muted">所选范围已全部听完，可重新选择范围。</p>}
        </div>
      ) : (
        <div className="continue-box">
          <p className="muted">继续听？选择数量：</p>
          <div className="row">
            <button className="btn" disabled={loadingMore}
              onClick={() => onLoadMore(5)}>再听 5 段</button>
            <button className="btn" disabled={loadingMore}
              onClick={() => onLoadMore(10)}>再听 10 段</button>
          </div>
          <div className="continue-custom">
            <input type="number" min={1} max={50} placeholder="自定义数量"
              value={moreCount} onChange={(e) => onCountChange(e.target.value)} />
            <button className="btn btn-primary" disabled={loadingMore || !count}
              onClick={() => onLoadMore(count)}>继续</button>
          </div>
          {notice && <p className="muted">{notice}</p>}
        </div>
      )}
    </div>
  );
}
