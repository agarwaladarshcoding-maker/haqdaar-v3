// The dashboard reads everything from the data door (tools/dashboard_api.py).
// These calls run on the dashboard's server side only; the browser never talks to the door.

export const DOOR = process.env.ENGINE_API ?? "http://127.0.0.1:8001";

export type Mark = { k: "ai" | "key" | "speech" | "silence" | "noise" | "problem"; s?: number; bad?: boolean };

export type CallRow = {
  key: string;
  call_id: string;
  at: string;
  lang: string;
  source: "phone" | "sim";
  duration_s: number;
  timed: boolean;
  turns: number;
  problems: number;
  unclear: number;
  live: boolean;
  verdict: { passed: boolean; reason: string } | null;
  strip: Mark[];
};

export type Need = { level: "bad" | "warn" | "info"; title: string; detail: string; page: string };

export type Home = {
  at: string;
  engine: {
    on: boolean;
    live_call: string | null;
    snapshot: string;
    snapshot_made: string;
    line: string;
    phone_tail: string;
  };
  numbers: {
    window: string;
    calls: number;
    judged: number;
    passed: number;
    avg_length_s: number | null;
    slowest_reply_s: number | null;
    reply_budget_s: number;
    all_calls: number;
    phone_calls: number;
  };
  needs: Need[];
  schemes: {
    chosen: number;
    checked: number;
    live: number;
    no_voice: number;
    set_aside: number;
    set_aside_slugs: string[];
    languages: Record<string, number>;
  };
  money: {
    muse: { day: string; today: number; day_cap: number; all: number; cap: number; blocked: boolean; open: boolean };
    units: { name: string; value: number; unit: string; note: string }[];
  };
  recent: CallRow[];
};

export async function getHome(): Promise<Home | null> {
  try {
    const r = await fetch(`${DOOR}/api/home`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
    return r.ok ? ((await r.json()) as Home) : null;
  } catch {
    return null; // the door is off: the page says so
  }
}

export const LANG: Record<string, string> = { hi: "Hindi", mr: "Marathi", en: "English" };

export function long(s: number): string {
  return s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.round(s * 10) / 10} s`;
}

export function when(at: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "no time";
  const day = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${day}, ${time}`;
}
