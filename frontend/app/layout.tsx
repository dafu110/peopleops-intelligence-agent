import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PeopleOps Intelligence Agent",
  description: "Professional PeopleOps intelligence console",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
