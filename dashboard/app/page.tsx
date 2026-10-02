import Link from "next/link";
import {
  BadgeCheck, ChevronRight, Info, OctagonAlert, Phone, PhoneCall, Timer, TriangleAlert, Zap, type LucideIcon,
} from "lucide-react";
import { DOOR, getHome, LANG, long, when, type Home, type Need } from "./lib/api";
import CallTape from "./ui/CallTape";

export const dynamic = "force-dynamic";

const NEED_ICON: Record<Need["level"], LucideIcon> = { bad: OctagonAlert, warn: TriangleAlert, info: Info };
const NEED_WORD: Record<Need["level"], string> = { bad: "Problem", warn: "Warning", info: "Note" };

function needHref(need: Need): { href: string; outside: boolean } | null {
  if (!need.page) return null;
  // Until the Calls page is built, a call opens in the first call page on the data door.
  if (need.page.startsWith("calls#")) return { href: `${DOOR}/#${need.page.slice(6)}`, outside: true };
  return { href: `/${need.page}`, outside: false };
}

function Line({ home }: { home: Home }) {
  const { engine, schemes } = home;
  const live = engine.live_call;
  const state = live ? "A call is live" : engine.on ? "Ready to call" : "The engine is off";
  const sub = live
    ? "One call at a time. The button comes back when this call ends."
    : engine.on
      ? `Rings the saved number${engine.phone_tail ? ` ending in ${engine.phone_tail}` : ""}, and shows the call as it happens.`
      : "No call can be placed until the engine is started in a terminal.";
  return (
    <section className="card line" aria-labelledby="line-h">
      <div className="line-main">
        <span className={`chip ${engine.on ? "chip-ok" : "chip-off"}`}>
          <span className={`dot ${engine.on ? "dot-ok" : "dot-off"}`} aria-hidden="true" />
          {engine.on ? "Engine on" : "Engine off"}
        </span>
        <h2 id="line-h" className="line-title">{state}</h2>
        <p className="line-sub">{sub}</p>
        <div className="line-act">
          {engine.on && !live ? (
            <Link className="btn" href="/live"><Phone size={17} aria-hidden="true" />Call my phone</Link>
          ) : (
            <button className="btn" disabled><Phone size={17} aria-hidden="true" />Call my phone</button>
          )}
          {live && <a className="btn btn-quiet" href={`${DOOR}/#${live}`}>Watch the call</a>}
          {!engine.on && !live && <span className="hint">Start it with <code>make run</code></span>}
        </div>
      </div>
      <dl className="facts">
        <div><dt>Schemes live on calls</dt><dd>{schemes.live}</dd></div>
        <div><dt>Outside callers</dt><dd>Not open yet</dd></div>
        <div><dt>Snapshot in use</dt><dd className="facts-small">{engine.snapshot || "none"}</dd></div>
      </dl>
    </section>
  );
}

function Stat({ icon: Icon, label, value, hint, tone }: {
  icon: LucideIcon; label: string; value: React.ReactNode; hint: string; tone?: "warn";
}) {
  return (
    <div className="stat">
      <span className="stat-icon" aria-hidden="true"><Icon size={18} strokeWidth={1.75} /></span>
      <dt className="stat-label">{label}</dt>
      <dd className={`stat-value${tone ? ` is-${tone}` : ""}`}>{value}</dd>
      <dd className="stat-hint">{hint}</dd>
    </div>
  );
}

function Numbers({ n }: { n: Home["numbers"] }) {
  const slow = n.slowest_reply_s;
  const none = <span className="dash" aria-label="none">–</span>;
  return (
    <section aria-labelledby="numbers-h">
      <h2 id="numbers-h" className="section-title">The {n.window}</h2>
      <dl className="stats">
        <Stat icon={PhoneCall} label="Calls" value={n.calls}
          hint={`${n.all_calls} in all, ${n.phone_calls} from a real phone`} />
        <Stat icon={BadgeCheck} label="Passed the judge"
          value={n.judged ? <>{n.passed}<small> of {n.judged}</small></> : none}
          hint={n.judged ? "Finished calls the judge checked" : "No finished call to judge"} />
        <Stat icon={Timer} label="Average length" value={n.avg_length_s == null ? none : long(n.avg_length_s)}
          hint={n.avg_length_s == null ? "Typed test calls are not timed" : "Timed calls only"} />
        <Stat icon={Zap} label="Slowest AI reply" value={slow == null ? none : `${slow} s`}
          tone={slow != null && slow > n.reply_budget_s ? "warn" : undefined}
          hint={`The budget is ${n.reply_budget_s} s`} />
      </dl>
    </section>
  );
}

function Needs({ needs }: { needs: Need[] }) {
  return (
    <section className="card" aria-labelledby="needs-h">
      <header className="card-head">
        <h2 id="needs-h" className="card-title">Needs a look</h2>
        <span className="count">{needs.length}</span>
      </header>
      {needs.length === 0 ? (
        <p className="quiet">Nothing needs you right now.</p>
      ) : (
        <ul className="needs">
          {needs.map((need, i) => {
            const Icon = NEED_ICON[need.level];
            const link = needHref(need);
            const body = (
              <>
                <span className={`need-icon need-${need.level}`}><Icon size={17} strokeWidth={1.9} aria-hidden="true" /></span>
                <span className="need-text">
                  <span className="need-title"><span className="sr-only">{NEED_WORD[need.level]}: </span>{need.title}</span>
                  <span className="need-detail">{need.detail}</span>
                </span>
                {link && <ChevronRight className="need-go" size={17} aria-hidden="true" />}
              </>
            );
            return (
              <li key={i}>
                {link
                  ? link.outside
                    ? <a className="need is-link" href={link.href}>{body}</a>
                    : <Link className="need is-link" href={link.href}>{body}</Link>
                  : <div className="need">{body}</div>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Schemes({ s }: { s: Home["schemes"] }) {
  const parts = [
    { name: "Live on calls", n: s.live, cls: "live" },
    { name: "Checked, no voice yet", n: s.no_voice, cls: "novoice" },
    { name: "Set aside", n: s.set_aside, cls: "aside" },
  ];
  const langs = Object.entries(s.languages);
  return (
    <section className="card" aria-labelledby="schemes-h">
      <header className="card-head">
        <h2 id="schemes-h" className="card-title">Schemes</h2>
        <Link className="card-link" href="/schemes">All {s.chosen}</Link>
      </header>
      <div className="split" role="img" aria-label={parts.map((p) => `${p.n} ${p.name}`).join(", ")}>
        {parts.filter((p) => p.n > 0).map((p) => (
          <span key={p.cls} className={`split-${p.cls}`} style={{ flexGrow: p.n }} />
        ))}
      </div>
      <ul className="legend">
        {parts.map((p) => (
          <li key={p.cls}>
            <span className={`swatch split-${p.cls}`} aria-hidden="true" />
            <span className="legend-name">{p.name}</span>
            <b>{p.n}</b>
          </li>
        ))}
      </ul>
      {langs.length > 0 && (
        <p className="foot">Passed the safety checks: {langs.map(([code, n]) => `${LANG[code] ?? code} ${n}`).join(", ")}</p>
      )}
    </section>
  );
}

function Meter({ label, value, cap }: { label: string; value: number; cap: number }) {
  const share = cap > 0 ? Math.min(value / cap, 1) : 0;
  return (
    <div className="meter">
      <div className="meter-top"><span>{label}</span><span className="num">₹{value.toFixed(2)} <small>of ₹{cap.toFixed(0)}</small></span></div>
      <div className="meter-bar" role="img" aria-label={`${label}: ${value.toFixed(2)} rupees of ${cap.toFixed(0)}`}>
        <span className={share >= 0.8 ? "is-warn" : ""} style={{ width: `${Math.max(share * 100, value > 0 ? 2 : 0)}%` }} />
      </div>
    </div>
  );
}

function Money({ m }: { m: Home["money"] }) {
  return (
    <section className="card" aria-labelledby="money-h">
      <header className="card-head">
        <h2 id="money-h" className="card-title">Money and use</h2>
        <span className={`chip ${m.muse.open ? "chip-ok" : "chip-warn"}`}>
          {m.muse.blocked ? "Muse blocked today" : m.muse.open ? "Muse open" : "Muse at its cap"}
        </span>
      </header>
      <Meter label="Muse today" value={m.muse.today} cap={m.muse.day_cap} />
      <Meter label="Muse in all" value={m.muse.all} cap={m.muse.cap} />
      <table className="units">
        <tbody>
          {m.units.map((u) => (
            <tr key={u.name}>
              <th scope="row">{u.name}<span className="units-note">{u.note}</span></th>
              <td className="num">{u.value.toLocaleString("en-IN")}<small>{u.unit}</small></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="foot">Only Muse is counted in rupees so far. The rest are counted in units.</p>
    </section>
  );
}

function Recent({ calls }: { calls: Home["recent"] }) {
  return (
    <section className="card" aria-labelledby="recent-h">
      <header className="card-head">
        <h2 id="recent-h" className="card-title">Last calls</h2>
        <Link className="card-link" href="/calls">All calls</Link>
      </header>
      {calls.length === 0 ? (
        <p className="quiet">
          No call has a trace yet. Run a typed test call with <code>make sim</code>, or place a real one, and it shows up here.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="calls">
            <thead>
              <tr><th>Call</th><th>When</th><th>Language</th><th className="col-tape">How it went</th><th>Length</th><th>Judge</th></tr>
            </thead>
            <tbody>
              {calls.map((c) => (
                <tr key={c.key}>
                  <td>
                    <a className="call-id" href={`${DOOR}/#${c.key}`}>{c.call_id}</a>
                    <span className="call-src">{c.source === "phone" ? "Phone" : "Typed test"}, {c.turns} turns</span>
                  </td>
                  <td className="nowrap">{when(c.at)}{c.live && <span className="chip chip-bad chip-gap">Live</span>}</td>
                  <td>{LANG[c.lang] ?? c.lang}</td>
                  <td className="col-tape">
                    <CallTape marks={c.strip} />
                    {(c.problems > 0 || c.unclear > 0) && (
                      <span className="tape-note">
                        {c.problems > 0 && `${c.problems} problem${c.problems > 1 ? "s" : ""}`}
                        {c.problems > 0 && c.unclear > 0 && ", "}
                        {c.unclear > 0 && `${c.unclear} not understood`}
                      </span>
                    )}
                  </td>
                  <td className="num nowrap">{c.timed ? long(c.duration_s) : <span className="quiet">Not timed</span>}</td>
                  <td>
                    {c.verdict
                      ? <span className={`chip ${c.verdict.passed ? "chip-ok" : "chip-bad"}`} title={c.verdict.reason}>{c.verdict.passed ? "Pass" : "Fail"}</span>
                      : <span className="quiet">Not judged</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="tape-legend" aria-label="How to read the tape">
        <li><span className="tape-ai" aria-hidden="true" />AI speaking</li>
        <li><span className="tape-key" aria-hidden="true" />Caller</li>
        <li><span className="tape-key is-bad" aria-hidden="true" />Not understood</li>
        <li><span className="tape-problem" aria-hidden="true" />Problem</li>
      </ul>
    </section>
  );
}

export default async function HomePage() {
  const home = await getHome();
  if (!home) {
    return (
      <>
        <header className="top"><div><h1 className="top-title">Home</h1></div></header>
        <section className="card later">
          <h2 className="card-title">The dashboard has no data</h2>
          <p>Its data door is not running. Start both with one command in the project folder:</p>
          <p><code>make dashboard</code></p>
        </section>
      </>
    );
  }
  return (
    <>
      <header className="top">
        <div>
          <h1 className="top-title">Home</h1>
          <p className="top-sub">Run the Haqdaar line and see how it is doing.</p>
        </div>
        <p className="top-note">Updated {home.at.slice(11, 16)}</p>
      </header>
      <div className="row row-top">
        <Line home={home} />
        <Schemes s={home.schemes} />
      </div>
      <Numbers n={home.numbers} />
      <div className="row row-mid">
        <Needs needs={home.needs} />
        <Money m={home.money} />
      </div>
      <Recent calls={home.recent} />
    </>
  );
}
