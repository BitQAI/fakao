"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconMine, IconReport, IconStudy } from "./icons";

const TABS = [
  { href: "/study", label: "学习", Icon: IconStudy },
  { href: "/report", label: "报告", Icon: IconReport },
  { href: "/settings", label: "我的", Icon: IconMine },
];

export default function BottomNav() {
  const pathname = usePathname();
  return (
    <nav className="bottom-nav">
      {TABS.map((t) => {
        const active = pathname === t.href;
        return (
          <Link key={t.href} href={t.href} className={`nav-item${active ? " active" : ""}`}>
            <span className="nav-icon"><t.Icon /></span>
            <span className="nav-label">{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
