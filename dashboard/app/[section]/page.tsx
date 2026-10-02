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
      <header className="top"><h1 className="top-title">{page.name}</h1></header>
      <section className="card later">
        <p className="later-step">Not built yet · step {page.step}</p>
        <h2>What this page will show</h2>
        <p>{page.will}</p>
        {page.slug === "calls" && (
          <p>Until then, calls open in the first call page: <a href={DOOR}>{DOOR}</a></p>
        )}
        <p><Link href="/">Back to Home</Link></p>
      </section>
    </>
  );
}
