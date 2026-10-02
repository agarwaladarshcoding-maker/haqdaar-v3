import type { Metadata } from "next";
import { Anek_Devanagari, Anek_Latin, Martian_Mono, Mukta } from "next/font/google";
import "./globals.css";
import { getHome } from "./lib/api";
import Refresh from "./ui/Refresh";
import Sidebar from "./ui/Sidebar";

// Signboard display face (Latin and Devanagari cut from the same family), a plain reading
// face that also covers Devanagari, and a mono for ids and timers.
const anekLatin = Anek_Latin({ subsets: ["latin"], axes: ["wdth"], variable: "--f-anek-latin", display: "swap" });
const anekDeva = Anek_Devanagari({ subsets: ["devanagari"], axes: ["wdth"], variable: "--f-anek-deva", display: "swap" });
const mukta = Mukta({ subsets: ["latin", "devanagari"], weight: ["400", "500", "600", "700"], variable: "--f-mukta", display: "swap" });
const mono = Martian_Mono({ subsets: ["latin"], variable: "--f-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Haqdaar control room",
  description: "Run and watch the Haqdaar phone line.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const home = await getHome();
  return (
    <html lang="en" className={`${anekLatin.variable} ${anekDeva.variable} ${mukta.variable} ${mono.variable}`}>
      <body>
        <div className="shell">
          <Sidebar engineOn={home ? home.engine.on : null} />
          <main className="main">{children}</main>
        </div>
        <Refresh />
      </body>
    </html>
  );
}
