"""Party labels to codes."""

import pytest

from councils.parse.parties import normalise


@pytest.mark.parametrize("label,code", [
    ("LAB", "LAB"), ("Labour", "LAB"), ("Lab", "LAB"), ("Labour & Co-operative", "LAB"), ("Labour Group", "LAB"),
    ("CON", "CON"), ("Conservative", "CON"), ("Conservative and Unionist", "CON"),
    ("LIBDEM", "LD"), ("Liberal Democrat", "LD"), ("Lib Dem", "LD"), ("Liberal Democrats", "LD"),
    ("Liberal", "LIB"), ("Green Party", "GRN"), ("REFUK", "REF"), ("Reform UK", "REF"), ("Plaid Cymru", "PC"),
    ("Independent", "IND"), ("IND", "IND"), ("Non-aligned", "IND"),
    ("Ashfield Independents", "LOCAL"), ("R4GV", "LOCAL"), ("Residents' Association", "LOCAL"),
    ("Your Party", "YP"), ("", "NONE"),
])
def test_normalise(label, code):
    assert normalise(label) == code


def test_unknown_label():
    assert normalise("Blue Moon Party") == ""
