import type { Mark } from "../lib/api";

const NAME: Record<Mark["k"], string> = {
  ai: "AI spoke",
  key: "key pressed",
  speech: "caller spoke",
  silence: "silence",
  noise: "noise",
  problem: "problem",
};

// A call drawn as a tape: a bar each time the AI spoke (longer bar, longer speech) and a tick
// each time the caller did something. Red is a problem, amber is "not understood".
export default function CallTape({ marks }: { marks: Mark[] }) {
  if (!marks.length) return <span className="tape-empty">nothing yet</span>;
  const said = marks.filter((m) => m.k === "ai").length;
  const did = marks.filter((m) => m.k !== "ai" && m.k !== "problem").length;
  return (
    <span className="tape" role="img" aria-label={`AI spoke ${said} times, caller acted ${did} times`}>
      {marks.map((m, i) => (
        <span
          key={i}
          className={`tape-${m.k}${m.bad ? " is-bad" : ""}`}
          style={m.k === "ai" ? { flexGrow: Math.max(m.s ?? 0, 1.5) } : undefined}
          title={m.k === "ai" && m.s ? `${NAME.ai} for ${m.s} s` : m.bad ? `${NAME[m.k]}, not understood` : NAME[m.k]}
        />
      ))}
    </span>
  );
}
