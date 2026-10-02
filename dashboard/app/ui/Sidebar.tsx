"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GROUPS } from "../lib/nav";

// Small line icons, one per page. 16 px box, drawn with the text colour.
const ICONS: Record<string, string> = {
  home: "M2 7.5 8 2.5l6 5V14H9.5v-4h-3v4H2z",
  phone: "M4 2h2.2l1 3-1.5 1.2a8 8 0 0 0 4.1 4.1L11 8.8l3 1V12a2 2 0 0 1-2.2 2A10.5 10.5 0 0 1 2 4.2 2 2 0 0 1 4 2z",
  list: "M2 3.5h12M2 8h12M2 12.5h12",
  book: "M3 2.5h7.5A2.5 2.5 0 0 1 13 5v8.5H5.5A2.5 2.5 0 0 1 3 11zM3 11a2.5 2.5 0 0 1 2.5-2.5H13",
  wave: "M1.5 8h1.5M5 4.5v7M8 2.5v11M11 5.5v5M13 8h1.5",
  coin: "M8 2a6 6 0 1 0 0 12A6 6 0 0 0 8 2zM6 6h4M6 8h4M8.5 6c1.5 0 1.5 2-0.5 2H6l3 3",
  gauge: "M2.5 11.5a6 6 0 1 1 11 0M8 9.5l3-4",
  map: "M2 4l4-1.5 4 1.5 4-1.5v9.5L10 13.5 6 12l-4 1.5zM6 2.5V12M10 4v9.5",
  chip: "M4.5 4.5h7v7h-7zM6.5 2v2.5M9.5 2v2.5M6.5 11.5V14M9.5 11.5V14M2 6.5h2.5M2 9.5h2.5M11.5 6.5H14M11.5 9.5H14",
  gear: "M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4",
};

function Icon({ name }: { name: string }) {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d={ICONS[name]} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Sidebar({ engineOn }: { engineOn: boolean | null }) {
  const path = usePathname();
  return (
    <aside className="side">
      <Link href="/" className="plate-mini" aria-label="Haqdaar, home">
        <span className="plate-mini-hi" lang="hi">हक़दार</span>
        <span className="plate-mini-en">Haqdaar · control room</span>
      </Link>
      <nav className="nav" aria-label="Pages">
        {GROUPS.map((group) => (
          <div className="nav-group" key={group.title || "last"}>
            {group.title && <div className="nav-title">{group.title}</div>}
            {group.pages.map((page) => {
              const href = `/${page.slug}`;
              const on = path === href;
              return (
                <Link key={page.slug} href={href} className={`nav-item${on ? " is-on" : ""}`} aria-current={on ? "page" : undefined}>
                  <Icon name={page.icon} />
                  <span>{page.name}</span>
                  {!page.built && <span className="nav-soon">{page.step}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="side-foot">
        <span className={`lamp ${engineOn ? "is-on" : engineOn === false ? "is-off" : "is-unknown"}`} aria-hidden="true" />
        <span>{engineOn ? "Engine is on" : engineOn === false ? "Engine is off" : "No data"}</span>
        <span className="side-foot-note">This computer only</span>
      </div>
    </aside>
  );
}
