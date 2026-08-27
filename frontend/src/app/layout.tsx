import type { Metadata } from "next";
import "./globals.css";
import BottomNav from "@/components/BottomNav";
import AiFab from "@/components/AiFab";

export const metadata: Metadata = {
  title: "法考冲刺",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <main className="page">{children}</main>
        <BottomNav />
        <AiFab />
      </body>
    </html>
  );
}
