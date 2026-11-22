"""Share cards for saved briefings and topic briefings: the link preview (``og:image`` on ``/b/<id>`` and on
``/topics/<slug>``) that shows the checking.

Each card is drawn once, with no AI, by wts-core's ``adapters.cards.briefing_card`` in the site's cloth, with the
site's icon, and kept on disk in the data folder's ``cards/``; after that the file is served. Its title is the site's
neutral title for the briefing ("Briefing from council minutes, 18 November 2026", ``api.plaintext.briefing_title``),
never the reader's question (docs/DECISIONS.md, 33), and its counts are the check strip's, from ``check_counts`` on the
answer as it is shown (``councils.rag.checks.shown``). A topic's card (decision 35) is titled with the topic's own
question, which the site wrote and which is never a reader's, as the family's account says ("a curated topic's card
has the topic's own question"): ``family/BRIEFINGS.md`` in the charity's repository (the review plan of 21 November
2026, B5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wts_core.checks import RULES_VERSION, CheckCounts, check_counts

from councils.config import STATIC_DIR
from councils.rag.checks import rechecked, shown

__all__ = ["RECORD", "card_png", "check_counts", "counts_in_words", "shown_counts", "topic_card_png"]

FONTS = STATIC_DIR / "fonts"
# Raise when what a card shows changes, so that cards already drawn are drawn again. The version of the checking
# rules is in the file's name too: a briefing judged again under new rules may show different counts.
CARD_VERSION = 1
CLOTH = (0x6E, 0x4A, 0x2A)  # Buckram brown, as on the site's band (the family kit's --wts-cloth-councils)
RECORD = "the council minutes"


def card_style(icon: Path | None) -> Any:
    from wts_core.adapters.cards import CardStyle

    return CardStyle(site_name="Where Councils Stand", domain="wherecouncilsstand.com", cloth=CLOTH, record=RECORD,
                     serif=FONTS / "SourceSerif4-Semibold.ttf", sans=FONTS / "SourceSans3-Regular.ttf",
                     sans_bold=FONTS / "SourceSans3-Semibold.ttf", icon=icon)


def shown_counts(events: list[dict[str, Any]]) -> CheckCounts | None:
    """The check strip's counts for a saved briefing as it is shown today, or None if it has no written answer
    (sources only, "No records found", or a briefing that failed)."""
    final = next((e for e in shown(rechecked(events)) if e.get("type") == "final"), None)
    answer = (final or {}).get("answer")
    if not isinstance(answer, dict) or answer.get("no_records") or not answer.get("segments"):
        return None
    return check_counts(answer)


def counts_in_words(counts: CheckCounts) -> str:
    """The counts as the strip says them, for the card's text alternative."""
    nosource = "sentence" if counts.no_source == 1 else "sentences"
    return (f"{counts.citations_matched} of {counts.citations_total} citations matched to the record, "
            f"{counts.quotes_found} of {counts.quotes_total} quotations found word for word, "
            f"{counts.no_source} {nosource} without a source")


def card_path(folder: Path, bid: str) -> Path:
    return folder / f"{bid}.v{CARD_VERSION}.r{RULES_VERSION}.png"


def card_png(folder: Path, bid: str, title: str, counts: CheckCounts, prepared: str, icon: Path | None) -> Path:
    """The card's file, drawn the first time it is asked for and kept. ``prepared`` is the day it was written, as
    the site writes dates ("18 November 2026")."""
    path = card_path(folder, bid)
    if not path.exists():
        from wts_core.adapters.cards import briefing_card

        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{id(path)}.tmp")
        tmp.write_bytes(briefing_card(card_style(icon), title=title, counts=counts, prepared=prepared))
        tmp.replace(path)
    return path


def topic_card_png(folder: Path, slug: str, bid: str, question: str, counts: CheckCounts, prepared: str,
                   icon: Path | None) -> Path:
    """A topic's card, for its current briefing: one for each briefing, so a new week's has its own, and the cards
    of the topic's earlier briefings are deleted as the new one is drawn. It is kept apart from the same briefing's
    card at ``/b/<id>``, which has the site's neutral title."""
    name = f"topic-{slug}-{bid}"
    path = card_path(folder, name)
    if not path.exists():
        prefix = f"topic-{slug}-"
        for old in folder.glob(f"{prefix}*.png"):
            # this topic's own (a briefing's id, then the versions), not one whose slug starts with this one's
            if len(old.name[len(prefix):].split(".v")[0]) == len(bid):
                old.unlink(missing_ok=True)
    return card_png(folder, name, question, counts, prepared, icon)
