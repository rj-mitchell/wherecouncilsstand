/** "Why use this rather than a chatbot?": one line under the question box, and a disclosure that opens to five
 * one-line points (the family's wording, in the charity's glossary). The same points are on the About and
 * How it works pages at more length (partials/why.html). Every claim here is true of this site's code and settings
 * (docs/DECISIONS.md, 23): change one only with the thing it describes. Nothing is counted when it is opened. */
export function Why() {
  return (
    <div className="why">
      <p>Answers only from the official record, every point linked and checked.</p>
      <details>
        <summary>Why use this rather than a chatbot?</summary>
        <ul>
          <li>
            <strong>Only the record.</strong> The AI that writes a briefing is given only the council minutes and
            votes found for your question, and may use nothing else.
          </li>
          <li>
            <strong>Every point linked and checked.</strong> Each point links to its source. Citations are checked
            against the source text, quotations word for word, and sentences no source supports are flagged.
          </li>
          <li>
            <strong>Up to date.</strong> Councils' minutes are read in every day.
          </li>
          <li>
            <strong>It says when there is nothing.</strong> If the record holds nothing relevant, you see "No records
            found", not a guess.
          </li>
          <li>
            <strong>Balanced by design.</strong> Evidence is chosen across councils run by different parties, not only
            by relevance.
          </li>
        </ul>
        <p>
          Briefings here are written by AI too. The difference is what the AI is given and how it is checked.{" "}
          <a href="/methodology#why">How it works</a>
        </p>
      </details>
    </div>
  );
}
