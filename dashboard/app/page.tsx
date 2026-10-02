import Link from "next/link";
import { DOOR, getHome, LANG, long, when, type Home, type Need } from "./lib/api";
import CallTape from "./ui/CallTape";
import Keypad from "./ui/Keypad";

export const dynamic = "force-dynamic";

function needHref(need: Need): { href: string; label: string; outside: boolean } | null {
  if (!need.page) return null;
  // Until the Calls page is built, a call opens in the old call page on the data door.
  if (need.page.startsWith("calls#")) return { href: `${DOOR}/#${need.page.slice(6)}`, label: "Open the call", outside: true };
  return { href: `/${need.page}`, label: "Go there", outside: false };
}

function Plate({ home }: { home: Home }) {
  const { engine, schemes } = home;
  const live = engine.live_call;
  const headline = live ? "A call is live" : engine.on ? "Ready to ring" : "The engine is off";
  const sub = live
    ? "One call at a time. The button comes back when this call ends."
    : engine.on
      ? `Rings the saved number${engine.phone_tail ? ` ending in ${engine.phone_tail}` : ""}. One call at a time.`
      : "No call can be placed. Start the engine in a terminal:";
  return (
    <section className="plate" aria-label="The line">
      <div className="plate-main">
        <p className="plate-eyebrow">
          <span className={`lamp ${engine.on ? "is-on" : "is-off"}`} aria-hidden="true" />
          The line · {engine.line}
        </p>
        <h1 className="plate-head">{headline}</h1>
        <p className="plate-sub">
          {sub} {!engine.on && !live && <code>make run</code>}
        </p>
        <div className="plate-act">
          {engine.on && !live ? (
            <Link className="call-btn" href="/live">Call my phone</Link>
          ) : (
            <button className="call-btn" disabled>Call my phone</button>
          )}
          {live && <a className="plate-link" href={`${DOOR}/#${live}`}>Watch it</a>}
        </div>
        <dl className="plate-facts">
          <div><dt>Schemes live on calls</dt><dd>{schemes.live}</dd></div>
          <div><dt>Snapshot</dt><dd className="mono">{engine.snapshot || "none"}</dd></div>
          <div><dt>Outside callers</dt><dd>not yet</dd></div>
        </dl>
      </div>
      <Keypad />
    </section>
  );
}

function Numbers({ n }: { n: Home["numbers"] }) {
  const slow = n.slowest_reply_s;
  return (
    <section className="register" aria-label={`Numbers for the ${n.window}`}>
      <header className="register-head">
        <h2>The {n.window}</h2>
        <p>{n.all_calls} calls in all · {n.phone_calls} from a real phone</p>
      </header>
      <dl className="register-row">
        <div><dt>Calls</dt><dd>{n.calls}</dd></div>
        <div>
          <dt>Passed the judge</dt>
          <dd>{n.judged ? <>{n.passed}<small> of {n.judged}</small></> : <span className="none">none judged</span>}</dd>
        </div>
        <div>
          <dt>Average length</dt>
          <dd>{n.avg_length_s == null ? <span className="none">not timed</span> : long(n.avg_length_s)}</dd>
        </div>
        <div>
          <dt>Slowest AI reply <small>budget {n.reply_budget_s} s</small></dt>
          <dd className={slow != null && slow > n.reply_budget_s ? "is-warn" : ""}>
            {slow == null ? <span className="none">not timed</span> : `${slow} s`}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Needs({ needs }: { needs: Need[] }) {
  return (
    <section className="card" aria-labelledby="needs-h">
      <header className="card-head">
        <h2 id="needs-h">Needs a look</h2>
        <span className="count">{needs.length}</span>
      </header>
      {needs.length === 0 ? (
        <p className="quiet">Nothing needs you right now.</p>
      ) : (
        <ul className="needs">
          {needs.map((need, i) => {
            const link = needHref(need);
            return (
              <li key={i} className={`need need-${need.level}`}>
                <span className="need-mark" aria-hidden="true" />
                <div>
                  <p className="need-title">{need.title}</p>
                  <p className="need-detail">{need.detail}</p>
                </div>
                {link && (link.outside
                  ? <a className="need-go" href={link.href}>{link.label}</a>
                  : <Link className="need-go" href={link.href}>{link.label}</Link>)}
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
        <h2 id="schemes-h">Schemes</h2>
        <Link className="card-link" href="/schemes">All {s.chosen}</Link>
      </header>
      <div className="split" role="img" aria-label={parts.map((p) => `${p.n} ${p.name}`).join(", ")}>
        {parts.filter((p) => p.n > 0).map((p) => (
          <span key={p.cls} className={`split-${p.cls}`} style={{ flexGrow: p.n }} />
        ))}
      </div>
      <ul className="legend">
        {parts.map((p) => (
          <li key={p.cls}><span className={`dot split-${p.cls}`} aria-hidden="true" /><b>{p.n}</b> {p.name}</li>
        ))}
      </ul>
      {langs.length > 0 && (
        <p className="foot">
          Passed the safety checks: {langs.map(([code, n]) => `${LANG[code] ?? code} ${n}`).join(" · ")}
        </p>
      )}
    </section>
  );
}

function Meter({ label, value, cap }: { label: string; value: number; cap: number }) {
  const share = cap > 0 ? Math.min(value / cap, 1) : 0;
  return (
    <div className="meter">
      <div className="meter-top"><span>{label}</span><span className="mono">₹{value.toFixed(2)} of ₹{cap.toFixed(0)}</span></div>
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
        <h2 id="money-h">Money and use</h2>
        <span className={`tag ${m.muse.open ? "tag-ok" : "tag-warn"}`}>{m.muse.blocked ? "Muse blocked today" : m.muse.open ? "Muse open" : "Muse at its cap"}</span>
      </header>
      <Meter label="Muse today" value={m.muse.today} cap={m.muse.day_cap} />
      <Meter label="Muse in all" value={m.muse.all} cap={m.muse.cap} />
      <table className="units">
        <tbody>
          {m.units.map((u) => (
            <tr key={u.name}>
              <th scope="row">{u.name}</th>
              <td className="mono">{u.value.toLocaleString("en-IN")} <small>{u.unit}</small></td>
              <td className="units-note">{u.note}</td>
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
    <section className="card card-wide" aria-labelledby="recent-h">
      <header className="card-head">
        <h2 id="recent-h">Last calls</h2>
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
              <tr><th>When</th><th>Call</th><th>Language</th><th className="col-tape">How it went</th><th>Length</th><th>Judge</th></tr>
            </thead>
            <tbody>
              {calls.map((c) => (
                <tr key={c.key}>
                  <td className="nowrap">{when(c.at)}{c.live && <span className="tag tag-live">live</span>}</td>
                  <td>
                    <a className="call-id mono" href={`${DOOR}/#${c.key}`}>{c.call_id}</a>
                    <span className="call-src">{c.source === "phone" ? "phone" : "typed test"} · {c.turns} turns</span>
                  </td>
                  <td>{LANG[c.lang] ?? c.lang}</td>
                  <td className="col-tape">
                    <CallTape marks={c.strip} />
                    {(c.problems > 0 || c.unclear > 0) && (
                      <span className="tape-note">
                        {c.problems > 0 && `${c.problems} problem${c.problems > 1 ? "s" : ""}`}
                        {c.problems > 0 && c.unclear > 0 && " · "}
                        {c.unclear > 0 && `${c.unclear} not understood`}
                      </span>
                    )}
                  </td>
                  <td className="mono nowrap">{c.timed ? long(c.duration_s) : <span className="none">not timed</span>}</td>
                  <td>
                    {c.verdict
                      ? <span className={`tag ${c.verdict.passed ? "tag-ok" : "tag-bad"}`} title={c.verdict.reason}>{c.verdict.passed ? "Pass" : "Fail"}</span>
                      : <span className="none">not judged</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="foot">
        In the tape, a bar is the AI speaking and a tick is the caller: a key, speech, or silence. Amber was not understood, red is a problem.
      </p>
    </section>
  );
}

export default async function HomePage() {
  const home = await getHome();
  if (!home) {
    return (
      <>
        <header className="top"><h1 className="top-title">Home</h1></header>
        <section className="card offline">
          <h2>The dashboard has no data</h2>
          <p>Its data door is not running. Start both with one command in the project folder:</p>
          <p><code>make dashboard</code></p>
        </section>
      </>
    );
  }
  return (
    <>
      <header className="top">
        <p className="top-title">Home</p>
        <p className="top-note">Updated {home.at.slice(11)} · refreshes by itself</p>
      </header>
      <Plate home={home} />
      <Numbers n={home.numbers} />
      <div className="grid">
        <Needs needs={home.needs} />
        <div className="stack">
          <Schemes s={home.schemes} />
          <Money m={home.money} />
        </div>
        <Recent calls={home.recent} />
      </div>
    </>
  );
}
