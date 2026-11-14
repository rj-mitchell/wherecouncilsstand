# Evaluation: the briefing test set

A fixed set of realistic questions, each with the reading a careful researcher would give it and, for some, what the
evidence must contain. Every change to how questions are read or how the minutes are searched can be scored against
it, so a change that helps one kind of question and quietly breaks another shows up. It was needed before the beta
(the family roadmap, X8); Where MPs Stand and Where Countries Stand keep sets like it, and `councils evaluate` is
adapted from Where Countries Stand's.

This is a starter set of 31 questions. Add to it whenever a real question is read badly or finds the wrong evidence:
the question as asked, and what it should have produced.

## What is scored

Nothing is written: no briefing, and no cost unless `--with-model` is given.

1. **Reading the question.** Each filter chosen is compared with `expect` in `eval/questions.toml`: the councils
   named, nations, kinds of council (county, district, unitary, metropolitan, London borough), kinds of meeting (full
   council, cabinet, policy committee), the party in overall control, councillors' parties, the dates (by year), and
   whether the question is about how councillors voted. A filter not listed is expected to be empty. "default" dates
   mean the site's default range, the last four years. `<field>_any` lists readings that are equally acceptable.
2. **The evidence.** For questions marked `no_records` (for example, a year before the record starts in May 2018),
   nothing should be found, so the briefing says "No records found." For questions with `include`, the sources found
   must include at least one from each council listed (by GSS code).

The questions cover topics with no filters, dates, each of the four nations, parties (who runs the council, and what
councillors of a party did), named councils and kinds of meeting, kinds of council, and a question about planning,
which the record doesn't hold.

## Running it

```bash
uv run councils evaluate                    # the built-in rules read each question (free)
uv run councils evaluate --with-model       # the model reads each question (a fraction of a penny each)
uv run councils evaluate --only kent-asylum --only tory-councils
```

It prints a line per question (`ok` or `--`, the number of sources, and what was wrong), then the totals by
category, and saves the full results under `eval/runs/` (not committed). On the server, the evidence is scored
against the full record:

```bash
cd /opt/wherecouncilsstand/deploy
docker compose run --rm -T app councils evaluate --no-save
```

The evidence checks mean something only on the full record. On your own computer, `scripts/fixture_site.py` makes a
small made-up record (three councils) that the questions can be read against, but the councils in `include` are
mostly not in it.

`--with-model` makes one call per question to the model that reads questions (the `query_parse_model` in
`config/settings.toml`), about 31 small calls. It is never run in CI.

## With each briefing written: `councils eval`

`councils evaluate` writes no briefing, so it cannot say whether a change made briefings better or worse. The
shared package's harness (`wts_core.eval`, with this site's questions and scoring: `CouncilsEval` in
`src/councils/evaluate.py`) asks every question of the real pipeline, has the model write each briefing, and
reports for each question and overall: what the checks found (citations that do not hold, sentences with no
citation, quotations not found word for word, loaded words), the spread of sources across the groups, the time to
the first word and to the end, and the cost. The two scores above (how the question was read, and the evidence) are
given beside them. A question is asked of the pipeline itself: never from the answer cache, never counted against
a reader's limits and never saved as a briefing.

```bash
uv run councils eval run                          # every question; saved under eval/runs/
uv run councils eval run --only bins-weekly --only kent-asylum
uv run councils eval run --record-fixtures eval/fixtures     # also keep each briefing, for replay
uv run councils eval compare eval/runs/A.json eval/runs/B.json
uv run councils eval replay eval/fixtures         # the checks again over kept briefings: free, no model
```

**It costs money.** A run makes two calls to the model for each question (one to read it, one to write the
briefing): 31 questions is roughly the cost of 31 briefings. No run starts without a limit: `[eval] max_cost_usd`
in `config/settings.toml` (2 US dollars), or `--max-cost`. Once the spending reaches the limit no further question
is asked, the rest are marked as not asked, and the run does not pass. It is never run in CI.

**What a run is held to** is `[eval.thresholds]` in `config/settings.toml`: no citation that does not hold, no
quotation that is not in its source word for word, and no question that ends in an error. The other figures
(grounded ratio, unsupported sentences, loaded words, the time taken) have no threshold yet: set them from the
first run on the full record. A run of the whole set that meets every threshold is noted in
`eval/runs/passed.jsonl`, with the id of the configuration it ran with (the same id the record of briefings gives
those settings: `councils stats` shows it). That file is committed, and is the only file under `eval/runs/` that
is: an experiment (two configurations tried side by side on readers) may only start with a configuration whose
pass is noted there.

**Replay.** `--record-fixtures` keeps, for each briefing written, what the model was given and what it wrote, with
the checks' report. `councils eval replay` runs the checks over those again and names every difference, each as
stricter, weaker or other; it ends with status 1 if anything that was flagged is no longer flagged. It is how a
change to the checks (in this site's `rag/checks.py`, or a new version of the shared package) is measured before it
ships, at no cost. Only briefings written from the test set are ever kept this way: never a reader's.

### The first run, on the server

A run needs the full record's search index and the API key, so it is made on the server. The container holds the
questions but not the repository, so the results are written to a folder of the server's and copied back:

```bash
cd /opt/wherecouncilsstand/deploy
mkdir -p eval-out
docker compose run --rm -T -v "$PWD/eval-out:/out" app \
  councils eval run --out /out/runs --record-fixtures /out/fixtures
```

Then, on your own computer, copy `eval-out/runs/` into the repository's `eval/runs/` and `eval-out/fixtures/` into
`eval/fixtures/`, and commit `eval/runs/passed.jsonl` (if the run passed) and `eval/fixtures/`. Record the run in
the table below. Until that first run there are no kept briefings to replay: `councils eval replay` has been run
only in the tests, on briefings a stand-in for the model wrote from the made-up record.

## Results

| Date | Run | Read right | Filters right | Evidence right | Notes |
|---|---|---|---|---|---|
| 6 November 2026 | built-in rules, on the made-up record | 29 of 31 | 277 of 279 | 3 of 6 (the made-up record lacks Leeds, Sheffield, Kent and Gwynedd) | "Tory councils" isn't read as councils run by the Conservatives (only "Tory-run" is); "unitary authorities" isn't read as unitary councils (only "unitary councils" and "unitaries") |

Record each run on the full record here, with the date and what changed.
