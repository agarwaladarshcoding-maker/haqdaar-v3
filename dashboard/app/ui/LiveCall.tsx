"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Keyboard, Phone, PhoneOff, Send, VolumeX } from "lucide-react";

type LiveState = {
  engine: { on: boolean; live_call: string | null; phone_tail: string };
  test: { key: string; active: boolean; error: string; waiting: "language" | "words" | "key" | null } | null;
};
type Item = {
  who: "ai" | "caller" | "note" | "problem";
  t: number;
  text?: string;
  parts?: { token: string; text: string; dur: number }[];
  dur?: number;
  reply_s?: number;
  kind?: string;
  understood?: string;
  cls?: string;
  turn_n?: number;
};
type Call = {
  key: string;
  info: {
    call_id: string; lang: string; source: "phone" | "sim"; timed: boolean; turns: number; unclear: number;
    problems: number; ended: string; finished: boolean; schemes: string[]; known: Record<string, string>;
    verdict: { passed: boolean; reason: string } | null;
  };
  items: Item[];
};

const LANG: Record<string, string> = { hi: "Hindi", mr: "Marathi", en: "English" };
const BOX: Record<string, string> = {
  category: "Topic", state: "State", gender: "Gender", social_category: "Social group", age: "Age",
  income_band: "Income", occupation: "Work", scheme: "Scheme named",
};
const WAITING: Record<string, string> = {
  language: "The AI is waiting for a language key: 1 Hindi, 2 Marathi, 3 English.",
  words: "The AI is listening. Type what the caller says, or a key.",
  key: "The AI is waiting for a key: 0 to 9, * or #.",
};
const TOOK: Record<string, string> = {
  ANSWER: "Understood", PROPOSAL: "Guessed, asking to confirm", UNCLEAR: "Not understood", NOISE: "Noise, no words",
  SILENCE: "Silence", REPEAT: "Asked to hear it again", CLARIFY: "Asked what it means", META: "Said something else",
};
const RING_WAIT_MS = 45000;

// "ANSWER · category = farming" from the engine, in plain words: "Understood: Topic = farming".
function took(cls: string | undefined, understood: string): string {
  const [, ...rest] = understood.split(" · ");
  const detail = rest
    .map((part) => {
      const [box, value] = part.split(" = ");
      return value === undefined ? part : `${BOX[box] ?? box} = ${value.replaceAll("_", " ")}`;
    })
    .join(", ");
  const word = TOOK[cls ?? ""] ?? cls ?? "";
  return detail ? `${word}: ${detail}` : word;
}

async function ask<T>(path: string, body?: object): Promise<{ ok: true; data: T } | { ok: false; why: string }> {
  try {
    const r = await fetch(`/api/door/${path}`, body
      ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }
      : { cache: "no-store" });
    const data = await r.json().catch(() => ({}));
    return r.ok ? { ok: true, data: data as T } : { ok: false, why: String(data.detail ?? `Error ${r.status}`) };
  } catch {
    return { ok: false, why: "The dashboard is not answering. Start it with: make dashboard" };
  }
}

function clock(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t - m * 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export default function LiveCall() {
  const [live, setLive] = useState<LiveState | null>(null);
  const [shown, setShown] = useState<string | null>(null); // the call on screen
  const [call, setCall] = useState<Call | null>(null);
  const [ringingSince, setRingingSince] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const talk = useRef<HTMLOListElement>(null);
  const typer = useRef<HTMLInputElement>(null);
  const started = useRef(false);
  const seen = useRef(0);

  const show = useCallback((key: string | null) => {
    setShown(key);
    setCall(null);
    seen.current = 0;
    window.history.replaceState(null, "", key ? `/live?call=${encodeURIComponent(key)}` : "/live");
  }, []);

  // Once a second: the engine, the phone call, the test call, and the call on screen.
  useEffect(() => {
    let stop = false;
    async function tick() {
      const state = await ask<LiveState>("live");
      if (stop) return;
      if (!state.ok) {
        setError(state.why);
        return;
      }
      setLive(state.data);
      let key = shown;
      if (!started.current) {
        started.current = true;
        key = new URLSearchParams(window.location.search).get("call")
          ?? (state.data.test?.active ? state.data.test.key : null)
          ?? state.data.engine.live_call;
        if (key) setShown(key);
      }
      const phone = state.data.engine.live_call;
      if (phone && ringingSince !== null) {
        setRingingSince(null);
        key = phone;
        show(phone);
      } else if (ringingSince !== null && Date.now() - ringingSince > RING_WAIT_MS) {
        setRingingSince(null);
        setError("The call did not connect. Run make calls to see what the phone company says.");
      }
      if (key) {
        const got = await ask<Call>(`calls/${encodeURIComponent(key)}`);
        if (!stop && got.ok) setCall(got.data);
      }
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [shown, ringingSince, show]);

  // Follow the talk down as it grows, unless the reader has scrolled up to read.
  const count = call?.items.length ?? 0;
  useEffect(() => {
    const el = talk.current;
    if (el && (seen.current === 0 || el.scrollHeight - el.scrollTop - el.clientHeight < 240)) el.scrollTop = el.scrollHeight;
    seen.current = count;
  }, [count]);

  const test = live?.test ?? null;
  const testActive = Boolean(test?.active);
  const phoneLive = live?.engine.live_call ?? null;
  const ringing = ringingSince !== null;
  const onScreenLive = shown !== null && ((testActive && test?.key === shown) || phoneLive === shown);
  const typing = testActive && test?.key === shown;

  // Put the cursor in the box when a test call starts, without making the page jump.
  useEffect(() => {
    if (typing) typer.current?.focus({ preventScroll: true });
  }, [typing]);

  async function ring() {
    setBusy(true);
    setError("");
    const r = await ask<{ sid: string }>("call-me", {});
    setBusy(false);
    if (r.ok) setRingingSince(Date.now());
    else setError(r.why);
  }

  async function startTest() {
    setBusy(true);
    setError("");
    const r = await ask<{ key: string }>("test-call", {});
    setBusy(false);
    if (r.ok) show(r.data.key);
    else setError(r.why);
  }

  async function send(what: string) {
    setError("");
    setText("");
    const r = await ask("test-call/input", { text: what });
    if (!r.ok) setError(r.why);
  }

  const engineOn = Boolean(live?.engine.on);
  const canRing = engineOn && !phoneLive && !testActive && !ringing && !busy;
  const tail = live?.engine.phone_tail;

  return (
    <>
      <div className="row row-starts">
        <section className="card" aria-labelledby="ring-h">
          <header className="card-head">
            <h2 id="ring-h" className="card-title">Call my phone</h2>
            <span className={`chip ${engineOn ? "chip-ok" : "chip-off"}`}>
              <span className={`dot ${engineOn ? "dot-ok" : "dot-off"}`} aria-hidden="true" />
              {live ? (engineOn ? "Engine on" : "Engine off") : "Checking"}
            </span>
          </header>
          <p className="quiet">
            Rings the saved number{tail ? ` ending in ${tail}` : ""}. Pick up, and the call shows below.
          </p>
          <div className="line-act">
            <button type="button" className="btn" onClick={ring} disabled={!canRing}>
              <Phone size={17} aria-hidden="true" />{ringing ? "Ringing your phone" : "Call my phone"}
            </button>
            {live && !engineOn && <span className="hint">Start the engine with <code>make run</code></span>}
            {phoneLive && <span className="hint">A call is live.</span>}
          </div>
        </section>

        <section className="card" aria-labelledby="test-h">
          <header className="card-head">
            <h2 id="test-h" className="card-title">Typed test call</h2>
            <span className="chip chip-off">Free</span>
          </header>
          <p className="quiet">No phone needed. You type what the caller presses or says, and the real engine answers.</p>
          <div className="line-act">
            <button type="button" className="btn btn-quiet" onClick={startTest} disabled={testActive || Boolean(phoneLive) || busy || !live}>
              <Keyboard size={17} aria-hidden="true" />{testActive ? "A test call is going on" : "Start a test call"}
            </button>
          </div>
        </section>
      </div>

      {(error || test?.error) && <p className="alert" role="alert">{error || test?.error}</p>}

      {!shown ? (
        <section className="card empty">
          <p className="card-title">No call on screen</p>
          <p className="quiet">Start one above. It appears here line by line: the AI on the left, the caller on the right.</p>
        </section>
      ) : (
        <div className="row row-live">
          <section className="card talk-card" aria-labelledby="talk-h">
            <header className="card-head">
              <h2 id="talk-h" className="card-title">The call</h2>
              <span className="chips">
                {call && <span className="chip chip-off">{call.info.source === "phone" ? "Phone" : "Typed test"}</span>}
                <span className={`chip ${onScreenLive ? "chip-bad" : "chip-off"}`}>
                  {onScreenLive && <span className="dot dot-live" aria-hidden="true" />}
                  {onScreenLive ? "Live" : "Ended"}
                </span>
              </span>
            </header>
            <ol className="talk" ref={talk} role="log" aria-label="The call, line by line">
              {!call || call.items.length === 0 ? (
                <li className="talk-note">Waiting for the first words.</li>
              ) : call.items.map((it, i) => {
                if (it.who === "note" || it.who === "problem") {
                  return <li key={i} className={`talk-note${it.who === "problem" ? " is-problem" : ""}`}>{it.text}</li>;
                }
                const ai = it.who === "ai";
                return (
                  <li key={i} className={`say ${ai ? "say-ai" : "say-caller"}`}>
                    <span className="say-who">
                      {ai ? "AI" : "Caller"}{call.info.timed && ` · ${clock(it.t)}`}
                    </span>
                    <div className="bubble">
                      {ai
                        ? it.parts?.map((p, j) => <p key={j} className={p.text ? "" : "bubble-token"}>{p.text || p.token}</p>)
                        : <p>{it.kind === "speech" ? `“${it.text}”` : it.text}</p>}
                    </div>
                    {ai && (it.dur || it.reply_s != null) ? (
                      <span className="say-meta">
                        {it.dur ? `Spoke for ${it.dur} s` : ""}{it.dur && it.reply_s != null ? " · " : ""}
                        {it.reply_s != null ? `replied in ${it.reply_s} s` : ""}
                      </span>
                    ) : null}
                    {!ai && it.understood && (
                      <span className={`chip ${it.cls === "UNCLEAR" || it.cls === "NOISE" ? "chip-warn" : it.cls === "SILENCE" ? "chip-off" : "chip-ok"}`}>
                        {took(it.cls, it.understood)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
            {typing ? (
              <form className="typer" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send(text.trim()); }}>
                <label htmlFor="typer-in" className="typer-label">What the caller presses or says</label>
                <div className="typer-row">
                  <input id="typer-in" ref={typer} className="input" value={text} onChange={(e) => setText(e.target.value)}
                    placeholder="1, or a few words" autoComplete="off" maxLength={300} />
                  <button type="submit" className="btn" disabled={!text.trim()}><Send size={16} aria-hidden="true" />Send</button>
                </div>
                <div className="typer-row">
                  <button type="button" className="btn btn-quiet btn-small" onClick={() => send("silence")}>
                    <VolumeX size={15} aria-hidden="true" />Say nothing
                  </button>
                  <button type="button" className="btn btn-quiet btn-small" onClick={() => send("hangup")}>
                    <PhoneOff size={15} aria-hidden="true" />Hang up
                  </button>
                  <span className="hint" aria-live="polite">{test?.waiting ? WAITING[test.waiting] : "The AI is talking."}</span>
                </div>
              </form>
            ) : call && !onScreenLive ? (
              <p className="foot">
                {call.info.ended ? `This call is over: ${call.info.ended}.` : "This call is over."} Start another above.
              </p>
            ) : null}
          </section>

          <section className="card" aria-labelledby="facts-h">
            <header className="card-head">
              <h2 id="facts-h" className="card-title">This call</h2>
              {call?.info.verdict && (
                <span className={`chip ${call.info.verdict.passed ? "chip-ok" : "chip-bad"}`}>
                  Judge: {call.info.verdict.passed ? "pass" : "fail"}
                </span>
              )}
            </header>
            {!call ? <p className="quiet">Nothing yet.</p> : (
              <>
                <dl className="pairs">
                  <div><dt>Language</dt><dd>{LANG[call.info.lang] ?? call.info.lang}</dd></div>
                  <div><dt>Turns</dt><dd>{call.info.turns}</dd></div>
                  <div><dt>Not understood</dt><dd className={call.info.unclear ? "is-warn" : ""}>{call.info.unclear}</dd></div>
                  <div><dt>Problems</dt><dd className={call.info.problems ? "is-bad" : ""}>{call.info.problems}</dd></div>
                </dl>
                <h3 className="sub-title">What the engine knows</h3>
                {Object.keys(call.info.known).length === 0 ? (
                  <p className="quiet">Nothing yet. Each answer it takes shows up here.</p>
                ) : (
                  <dl className="pairs pairs-wide">
                    {Object.entries(call.info.known).map(([box, value]) => (
                      <div key={box}><dt>{BOX[box] ?? box}</dt><dd>{String(value).replaceAll("_", " ")}</dd></div>
                    ))}
                  </dl>
                )}
                <h3 className="sub-title">Schemes read out</h3>
                {call.info.schemes.length === 0
                  ? <p className="quiet">None yet.</p>
                  : <ul className="plain">{call.info.schemes.map((name, i) => <li key={i}>{name}</li>)}</ul>}
                {call.info.verdict && <p className="foot">Judge: {call.info.verdict.reason}</p>}
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
