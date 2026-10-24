"""Which committees are in the record (docs/DECISIONS.md, 3)."""

import pytest

from councils.committees import kind, strip_prefix


@pytest.mark.parametrize("title", [
    "Council", "Full Council", "County Council", "Council Meeting", "Meeting of the Council", "Annual Council",
    "Budget Council", "Extraordinary Council", "Council - Extraordinary", "City Council", "Borough Council",
    "Annual Meeting of the Council", "Cyngor", "Ordinary Council", "Full Council - Council questions",
    "Full Council Annual General Meeting", "Annual Meeting of Council", "Extraordinary Meeting of the Council",
])
def test_full_council(title):
    assert kind(title) == "council"


@pytest.mark.parametrize("title", [
    "Cabinet", "Executive", "Executive Board", "Mayor and Cabinet", "Cabinet (Executive)", "The Cabinet",
    "Cabinet - Special",
])
def test_cabinet(title):
    assert kind(title) == "cabinet"


@pytest.mark.parametrize("title", [
    "Policy and Resources Committee", "Strategy & Resources Committee", "Policy & Finance Committee",
    "Corporate Policy and Resources Committee",
])
def test_committee_system(title):
    assert kind(title) == "policy"


@pytest.mark.parametrize("title", [
    "Planning Committee", "Cabinet Member for Highways decisions", "Licensing Sub-Committee",
    "Council Tax Support Working Group", "Overview and Scrutiny Committee", "Cabinet Advisory Panel",
    "Council Housing Committee", "Audit and Governance Committee", "Executive Member Decisions",
])
def test_out_of_scope(title):
    assert kind(title) is None


def test_shared_site_prefix():
    assert strip_prefix("Babergh Cabinet", ["Babergh"]) == "Cabinet"
    assert strip_prefix("Mid Suffolk Council", ["Babergh"]) is None
    assert strip_prefix("Mid Suffolk Council", ["Mid Suffolk"]) == "Council"
