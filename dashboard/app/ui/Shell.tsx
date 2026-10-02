"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AudioLines, BookOpen, Cpu, Gauge, House, IndianRupee, Map, PanelLeftClose, PanelLeftOpen,
  PhoneCall, ScrollText, Settings, type LucideIcon,
} from "lucide-react";
import { GROUPS } from "../lib/nav";

const ICONS: Record<string, LucideIcon> = {
  home: House, phone: PhoneCall, list: ScrollText, book: BookOpen, wave: AudioLines,
  coin: IndianRupee, gauge: Gauge, map: Map, chip: Cpu, gear: Settings,
};
const KEY = "haqdaar.menu"; // "small" when the left bar is folded to icons

// The frame of every page: the left bar (full, or folded to icons) and the page beside it.
export default function Shell({ engineOn, children }: { engineOn: boolean | null; children: React.ReactNode }) {
  const path = usePathname();
  const [small, setSmall] = useState(false);

  useEffect(() => {
    try {
      setSmall(localStorage.getItem(KEY) === "small");
    } catch {
      /* no storage: the bar just starts open */
    }
  }, []);

  function toggle() {
    setSmall((was) => {
      try {
        localStorage.setItem(KEY, was ? "full" : "small");
      } catch {
        /* not saved; it still folds for this visit */
      }
      return !was;
    });
  }

  const engine = engineOn ? "Engine is on" : engineOn === false ? "Engine is off" : "No data";
  return (
    <div className="shell" data-small={small}>
      <aside className="side">
        <Link href="/" className="brand" aria-label="Haqdaar, home">
          <span className="brand-mark" lang="hi" aria-hidden="true">ह</span>
          <span className="brand-name side-text">Haqdaar</span>
        </Link>
        <nav className="nav" aria-label="Pages">
          {GROUPS.map((group, g) => (
            <ul className="nav-group" key={g}>
              {group.pages.map((page) => {
                const href = `/${page.slug}`;
                const on = path === href;
                const Icon = ICONS[page.icon];
                return (
                  <li key={page.slug}>
                    <Link
                      href={href}
                      className={`nav-item${on ? " is-on" : ""}`}
                      aria-current={on ? "page" : undefined}
                      aria-label={page.name}
                      title={small ? page.name : undefined}
                    >
                      <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
                      <span className="side-text">{page.short ?? page.name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          ))}
        </nav>
        <div className="side-foot">
          <div className="side-engine" title={small ? engine : undefined}>
            <span className={`dot ${engineOn ? "dot-ok" : engineOn === false ? "dot-off" : "dot-none"}`} aria-hidden="true" />
            <span className="side-text">{engine}</span>
            {small && <span className="sr-only">{engine}</span>}
          </div>
          <button type="button" className="nav-item fold" onClick={toggle} aria-expanded={!small} aria-label={small ? "Open the menu" : "Fold the menu"}>
            {small ? <PanelLeftOpen size={18} strokeWidth={1.75} aria-hidden="true" /> : <PanelLeftClose size={18} strokeWidth={1.75} aria-hidden="true" />}
            <span className="side-text">Fold menu</span>
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
