"""Briefings are streamed with a comment line during long silences, so a proxy does not close the connection, and the
work stops once the reader has gone. From Where MPs Stand's tests/test_sse.py and Where Countries Stand's
tests/test_api.py: the streamer is the same code in all three."""

import threading
import time

import pytest

from councils.api.app import sse


def test_a_silence_is_filled_with_comment_lines_and_events_arrive_in_order():
    def events():
        yield {"type": "plan", "n": 1}
        time.sleep(0.35)  # the model thinking
        yield {"type": "final", "n": 2}

    out = list(sse(events(), keep_alive=0.1))
    assert out[0].startswith(b"event: plan\ndata: ")
    assert out[-1].startswith(b"event: final\ndata: ")
    assert out[1:-1] and all(c == b": still working\n\n" for c in out[1:-1])


def test_an_error_is_raised_where_the_response_is_sent():
    def events():
        yield {"type": "plan"}
        raise RuntimeError("boom")

    stream = sse(events(), keep_alive=1)
    next(stream)
    with pytest.raises(RuntimeError):
        next(stream)


def test_the_work_stops_once_the_reader_has_gone():
    closed = threading.Event()

    def events():
        try:
            for i in range(1000):
                yield {"type": "text", "text": str(i)}
                time.sleep(0.01)
        finally:
            closed.set()

    stream = sse(events(), keep_alive=1)
    next(stream)
    stream.close()  # the reader left
    assert closed.wait(2)


def test_stream_stops_when_the_reader_leaves():
    """A briefing nobody is reading any more must stop being written: its events are closed, which closes the
    model's stream (found on Where Countries Stand's live site: a reader who left kept the briefing running, and
    paid for)."""
    closed = threading.Event()
    made = []

    def briefing():
        try:
            while True:
                made.append(1)
                yield {"type": "text", "text": "word "}
                time.sleep(0.01)
        finally:
            closed.set()

    events = briefing()  # held here, so only an explicit close (not the garbage collector) can stop it
    out = sse(events, keep_alive=1)
    assert next(out).startswith(b"event: text")
    out.close()  # the reader has gone: the server closes the response
    assert closed.wait(2)
    n = len(made)
    time.sleep(0.1)
    assert len(made) == n  # nothing more is written


def test_dates_are_written_as_text():
    from datetime import date

    out = list(sse(iter([{"type": "sources", "date": date(2025, 2, 26)}]), keep_alive=1))
    assert out == [b'event: sources\ndata: {"type": "sources", "date": "2025-02-26"}\n\n']
