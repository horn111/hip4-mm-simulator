import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";

import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://hip4-mm-simulator.vercel.app"),
  title: "HIP-4 MM Simulator — Inspect every paper fill",
  description:
    "A deterministic, queue-aware execution simulator for Hyperliquid HIP-4 market makers.",
  applicationName: "HIP-4 MM Simulator",
  alternates: { canonical: "/" },
  openGraph: {
    title: "See exactly when a HIP-4 paper order earns a fill",
    description:
      "Replay observed L2, aggressor trades, queue consumption, and spot-safe fills.",
    type: "website",
    url: "/",
    siteName: "HIP-4 MM Simulator",
  },
  twitter: {
    card: "summary_large_image",
    title: "HIP-4 MM Simulator",
    description: "Transparent, deterministic HIP-4 execution simulation.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body>
        <TooltipProvider>{children}</TooltipProvider>
        <Analytics />
      </body>
    </html>
  );
}
