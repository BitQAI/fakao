"use client";

/** 知识点搜索框：受控输入 + 清空 + 可选命中数提示。 */
export default function KeywordSearch({
  value, onChange, placeholder, hint,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string | null;
}) {
  const active = value.trim().length > 0;
  return (
    <div className="search-bar">
      <input
        className="search-input"
        value={value}
        placeholder={placeholder ?? "搜索知识点…"}
        onChange={(e) => onChange(e.target.value)}
      />
      {active && (
        <button className="search-clear" onClick={() => onChange("")} aria-label="清空搜索">
          ×
        </button>
      )}
      {active && hint && <span className="search-hint">{hint}</span>}
    </div>
  );
}
