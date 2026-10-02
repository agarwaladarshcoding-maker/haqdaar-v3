import type { Metadata } from "next";
import { Inter, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { getHome } from "./lib/api";
import Refresh from "./ui/Refresh";
import Shell from "./ui/Shell";

// One plain face for everything. Hindi and Marathi words fall through to its Devanagari partner.
const inter = Inter({ subsets: ["latin"], variable: "--f-inter", display: "swap" });
const deva = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--f-deva", display: "swap" });

export const metadata: Metadata = {
  title: "Haqdaar",
  description: "Run and watch the Haqdaar phone line.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const home = await getHome();
  return (
    <html lang="en" className={`${inter.variable} ${deva.variable}`}>
      <body>
        <Shell engineOn={home ? home.engine.on : null}>{children}</Shell>
        <Refresh />
      </body>
    </html>
  );
}
