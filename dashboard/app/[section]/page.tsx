import Link from "next/link";
import { notFound } from "next/navigation";
import { DOOR } from "../lib/api";
import { PAGES } from "../lib/nav";

// Every page in the left bar that is not built yet lands here and says what it will show.
export default async function Section({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const page = PAGES.find((p) => p.slug === section && !p.built);
  if (!page) notFound();
  return (
    <>
      <header className="top">
        <div>
          <h1 className="top-title">{page.name}</h1>
          <p className="top-sub">Not built yet. It comes in step {page.step}.</p>
        </div>
      </header>
      <section className="card later">
        <h2 className="card-title">What this page will show</h2>
        <p>{page.will}</p>
        {page.slug === "calls" && (
          <p>Until then, calls open in the first call page: <a href={DOOR}>{DOOR}</a></p>
        )}
        <p><Link href="/">Back to Home</Link></p>
      </section>
    </>
  );
}
