/** 内联 SVG 图标集（无外部依赖，stroke 跟随 currentColor）。 */

interface IconProps { size?: number }

function base(size: number) {
  return {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
}

export function IconStudy({ size = 21 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M4 19V5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-2z" />
      <path d="M8 7h8M8 11h8M8 15h5" />
    </svg>
  );
}

export function IconReport({ size = 21 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M4 20V10M10 20V4M16 20v-8M22 20H2" />
    </svg>
  );
}

export function IconLaw({ size = 21 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M12 3v18" />
      <path d="M5 7h14" />
      <path d="M7 7l-3 7h6z" />
      <path d="M17 7l-3 7h6z" />
      <path d="M8 21h8" />
    </svg>
  );
}

/** 案例：卷宗 + 文本行 */
export function IconCase({ size = 21 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M7 3h8l4 4v14H7z" />
      <path d="M15 3v4h4" />
      <path d="M10 12h6M10 16h4" />
    </svg>
  );
}

export function IconMine({ size = 21 }: IconProps) {
  return (
    <svg {...base(size)}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" />
    </svg>
  );
}

export function IconAi({ size = 24 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z" />
      <path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
      <path d="M5 16l.6 1.6 1.6.6-1.6.6L5 20.4 4.4 18.8 2.8 18.2l1.6-.6z" />
    </svg>
  );
}
