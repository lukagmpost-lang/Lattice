"""Tests for the canonical Cuyahoga name/entity parser."""

import pytest

from osi.names import (
    age_at_case,
    caption_sides,
    case_year,
    identities_match,
    is_organization,
    other_side_parties,
    parse_person,
    party_key,
    person_identity,
    person_key,
    split_parties,
)


def test_generational_suffix_is_not_a_surname():
    assert party_key("HENRY CURRIE JR") == "owner|CURRIE, HENRY"
    assert party_key("SMITH, JOHN, JR") == "owner|SMITH, JOHN"
    assert parse_person("HENRY CURRIE JR")[3] == "JR"


def test_natural_and_comma_order_agree():
    assert person_key("JOHN SMITH") == person_key("SMITH, JOHN")
    assert party_key("CO, MARY") == "owner|CO, MARY"


def test_joint_parties_are_split_but_corporations_are_not():
    assert split_parties("FRAN HARBERT & MARK BOYNTON") == [
        "FRAN HARBERT",
        "MARK BOYNTON",
    ]
    assert split_parties("SMITH AND JONES LLC") == ["SMITH AND JONES LLC"]
    assert split_parties("BLUE CROSS & BLUE SHIELD") == ["BLUE CROSS & BLUE SHIELD"]


def test_shared_surname_shorthand():
    assert split_parties("DAVID W & HEATHER WAGNER") == [
        "DAVID W WAGNER",
        "HEATHER WAGNER",
    ]
    assert split_parties("SMITH, JOHN AND MARY") == ["SMITH, JOHN", "MARY SMITH"]
    # Two full names do not share a surname.
    assert split_parties("JOHN SMITH & JANE DOE") == ["JOHN SMITH", "JANE DOE"]


def test_alias_keeps_the_legal_name():
    assert party_key("NATHAN WILLIAMS AKA NATHAN GUERRY") == "owner|WILLIAMS, NATHAN"


def test_caption_noise_is_removed():
    assert party_key("JOHN SMITH ET AL") == "owner|SMITH, JOHN"
    assert party_key("FORD, JOHN ET., AL") == "owner|FORD, JOHN"
    assert party_key("SMITH, JOHN, TRUSTEE") == "owner|SMITH, JOHN"


def test_organization_detection():
    assert is_organization("SMITH AND JONES LLC")
    assert is_organization("ESTATE OF JOHN SMITH")
    assert is_organization("BANK OF AMERICA NA")
    assert not is_organization("CO, MARY")
    assert not is_organization("JOHN SMITH")


def test_caption_sides_and_opponents():
    caption = "SMITH, JOHN v. JONES, MARY ET AL"
    assert caption_sides(caption) == ("SMITH, JOHN", "JONES, MARY ET AL")
    assert other_side_parties(caption, person_key("SMITH, JOHN")) == ["JONES, MARY"]
    assert other_side_parties("JOHN SMITH v JANE ROE", person_key("SMITH, JOHN")) == [
        "JANE ROE"
    ]
    assert other_side_parties("no caption separator", "owner|SMITH, JOHN") == []


def test_case_year_formats():
    assert case_year("CV-87-12345") == 1987
    assert case_year("2016ML29035") == 2016
    assert case_year("DR-16-12345") == 2016
    assert case_year("12345") is None


def test_identity_matching_uses_middle_only_when_both_have_it():
    left = person_identity("MCGOWAN, MICHAEL JAMES")
    same = person_identity("MICHAEL J MCGOWAN")
    conflict = person_identity("MICHAEL A MCGOWAN")
    assert identities_match(left, same)
    assert not identities_match(left, conflict)
    assert identities_match(person_identity("SMITH, JOHN"), person_identity("JOHN SMITH"))


def test_suffix_conflict_is_rejected():
    assert not identities_match(
        person_identity("HENRY CURRIE JR"), person_identity("HENRY CURRIE SR")
    )
    assert identities_match(
        person_identity("HENRY CURRIE JR"), person_identity("HENRY CURRIE")
    )


def test_age_at_case():
    assert age_at_case("1950-01-01", "2016ML1") is True
    assert age_at_case("2010-01-01", "2016ML1") is False
    assert age_at_case(None, "2016ML1") is None
