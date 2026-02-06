// frontend/app/layout.tsx
// 功能: 根布局组件，定义全局样式和字体

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ 
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "内容生产系统",
  description: "AI Agent 驱动的商业内容生产平台",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body
        className={`${inter.variable} font-sans antialiased bg-surface-0 text-zinc-100`}
      >
        {children}
      </body>
    </html>
  );
}

