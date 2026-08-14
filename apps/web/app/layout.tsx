import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"),
  title: { default: "PatchPilot · Maintainer control center", template: "%s · PatchPilot" },
  description: "Assign an issue from Slack. Approve the plan from Telegram. Receive a tested draft pull request on GitHub.",
  openGraph: {
    title: "PatchPilot · Maintainer control center",
    description: "Assign on Slack. Approve on Telegram. Ship a tested draft PR.",
    images: [{ url: "/og.png", width: 1792, height: 922, alt: "PatchPilot cross-channel maintainer workflow" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "PatchPilot · Maintainer control center",
    description: "Assign on Slack. Approve on Telegram. Ship a tested draft PR.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{document.documentElement.setAttribute('data-theme', localStorage.getItem('patchpilot-theme') || 'light')}catch(e){}`,
          }}
        />
      </head>
      <body><Providers><AppShell>{children}</AppShell></Providers></body>
    </html>
  );
}
