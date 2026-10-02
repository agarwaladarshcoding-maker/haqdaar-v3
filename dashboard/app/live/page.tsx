import LiveCall from "../ui/LiveCall";

export const dynamic = "force-dynamic";

export default function LivePage() {
  return (
    <>
      <header className="top">
        <div>
          <h1 className="top-title">Live call</h1>
          <p className="top-sub">Start a call and watch it here as it happens.</p>
        </div>
      </header>
      <LiveCall />
    </>
  );
}
