import type { Metadata } from "next";
import "@fontsource/lato/400.css";
import "@fontsource/lato/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Open—GrokBot · Persistent AI teammates",
  description: "Create and work with durable, local-first AI teammates.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
