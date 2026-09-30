import Link from "next/link";

export default function Home() {
  return (
    <div className="workspace">
      <header className="masthead">
        <Link href="/" className="wordmark" aria-label="Lattice home">lattice<span aria-hidden="true">.</span></Link>
        <span className="status">Project foundation</span>
      </header>
      <main id="main" tabIndex={-1}>
        <p className="eyebrow">A cited knowledge workspace</p>
        <h1>A place for knowledge.<br />{" "}And its sources.</h1>
        <p className="intro">Bring your documents together. Ask with context. Follow every answer back to the evidence.</p>
        <section className="reading-card" aria-labelledby="foundation-title">
          <span className="chapter" aria-hidden="true">01 / THE FOUNDATION</span>
          <h2 id="foundation-title">The reading room is taking shape.</h2>
          <p>This is the starting point for Lattice. Uploads, search, and cited answers are not available yet.</p>
          <p>The next step is accounts and collection access, followed by document ingestion and source inspection.</p>
          <div className="note"><span aria-hidden="true">↳</span> Answer generation unavailable</div>
        </section>
        <p className="principle">A useful answer should always come with a way to check it.</p>
      </main>
      <footer>Built for careful reading.<span lang="ne">ज्ञान र त्यसका स्रोतहरू।</span></footer>
    </div>
  );
}
