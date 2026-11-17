/** The line about the briefings beside the question box, and a disclosure that opens to the family's first five
 * points (the charity's glossary, "AI briefings"). The About and methodology pages have all seven, at more length
 * (partials/why.html). Every claim here is true of this site's code and settings (docs/DECISIONS.md, 23): change one
 * only with the thing it describes. */
export function Why() {
  return (
    <div className="why panel">
      <p>Briefings are written by AI from the official record only, and every citation is checked.</p>
      <details>
        <summary>How the briefings are checked</summary>
        <ul>
          <li>The AI is given only the council minutes and votes found for your question and may use nothing else.</li>
          <li>
            Each point links to its source. Citations are checked against the source text, quotations are checked
            word for word, and sentences that no source supports are flagged.
          </li>
          <li>Councils’ minutes are read in every day.</li>
          <li>If the record holds nothing relevant, the site says “No records found”.</li>
          <li>Evidence is drawn from across councils run by different parties.</li>
        </ul>
        <p>
          <a href="/methodology#ai-briefings">More about the briefings</a>
        </p>
      </details>
    </div>
  );
}
