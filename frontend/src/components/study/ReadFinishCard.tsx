"use client";

interface Props {
  customMode: boolean;
  queueLabel: string;
  itemsCount: number;
  reviewedCount: number;
  remaining: number;
  loadingMore: boolean;
  continueCount: string;
  notice: string;
  onCountChange: (value: string) => void;
  onPickRange: () => void;
  /** 自定义范围内继续下一组（limit 条） */
  onContinueRange: (limit: number) => void;
  /** 今日计划之外继续续学 N 条 */
  onLoadMore: (count: number) => void;
}

/** 看背队列学完后的收尾卡：与原先的「今日卡片已看完 / 自定义范围已学完」一致。 */
export default function ReadFinishCard({
  customMode, queueLabel, itemsCount, reviewedCount, remaining, loadingMore,
  continueCount, notice, onCountChange, onPickRange, onContinueRange, onLoadMore,
}: Props) {
  const head = queueLabel ? `${queueLabel}完成` : customMode ? "自定义范围已学完" : "今日卡片已看完";
  const custom = Number(continueCount);
  return (
    <div className="card center">
      <h2>{head}</h2>
      <p className="muted">共 {itemsCount} 张 · 今日累计 {reviewedCount} 条，已记录自评。</p>
      {customMode ? (
        <div>
          <div className="row">
            {queueLabel
              ? <a className="btn btn-primary" href="/study?view=wrong">回到错题本</a>
              : <button className="btn btn-primary" onClick={onPickRange}>重新选择范围</button>}
          </div>
          {remaining > 0 ? (
            <div className="continue-box">
              <p className="muted">剩余未学 {remaining} 条，选择下一组或部分：</p>
              <div className="row">
                <button className="btn" disabled={loadingMore}
                  onClick={() => onContinueRange(20)}>下一组 20</button>
                <button className="btn" disabled={loadingMore}
                  onClick={() => onContinueRange(50)}>下一组 50</button>
              </div>
              <div className="continue-custom">
                <input type="number" min={1} max={50} placeholder="自定义数量"
                  value={continueCount} onChange={(e) => onCountChange(e.target.value)} />
                <button className="btn btn-primary" disabled={loadingMore || !custom}
                  onClick={() => onContinueRange(custom)}>继续</button>
              </div>
              {notice && <p className="muted">{notice}</p>}
            </div>
          ) : (
            <p className="muted">所选范围已全部学完，可重新选择范围继续学习。</p>
          )}
        </div>
      ) : (
        <div className="continue-box">
          <p className="muted">还想继续学？选择数量：</p>
          <div className="row">
            <button className="btn" disabled={loadingMore}
              onClick={() => onLoadMore(5)}>继续 5 个</button>
            <button className="btn" disabled={loadingMore}
              onClick={() => onLoadMore(10)}>继续 10 个</button>
          </div>
          <div className="continue-custom">
            <input type="number" min={1} max={50} placeholder="自定义数量"
              value={continueCount} onChange={(e) => onCountChange(e.target.value)} />
            <button className="btn btn-primary" disabled={loadingMore || !custom}
              onClick={() => onLoadMore(custom)}>继续</button>
          </div>
        </div>
      )}
    </div>
  );
}
