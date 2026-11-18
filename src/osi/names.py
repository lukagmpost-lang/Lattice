"""Canonical person and organization name handling.

The Cuyahoga loaders used to each carry a slightly different parser.  That
made the same person appear as ``owner|SMITH, JOHN`` in one pass and
``owner|JOHN, SMITH`` in another, and it turned suffixes such as ``JR`` into
surnames.  This module is the single place for those rules now.

The functions here intentionally stay independent of NetworkX so they can be
tested without a graph and reused by the scrapers.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import NamedTuple

# Suffixes that follow a person's name.  They are never surnames.
GENERATIONAL_SUFFIXES = {
    "JR",
    "JR.",
    "SR",
    "SR.",
    "II",
    "III",
    "IV",
    "V",
}

# Legal/organizational suffixes.  A token match is enough; the caller does not
# have to know where in the string the suffix appears.
ORG_TOKENS = {
    "LLC",
    "L.L.C",
    "L.L.C.",
    "INC",
    "INC.",
    "INCORPORATED",
    "CORP",
    "CORP.",
    "CORPORATION",
    "COMPANY",
    "CO",
    "CO.",
    "LP",
    "L.P",
    "L.P.",
    "LLP",
    "L.L.P",
    "L.L.P.",
    "LTD",
    "LTD.",
    "LIMITED",
    "PLLC",
    "P.C",
    "P.C.",
    "PC",
    "TRUST",
    "TRUSTEE",
    "TRS",
    "ASSOCIATION",
    "ASSN",
    "ASSN.",
    "BANK",
    "CREDIT",
    "UNION",
    "FEDERAL",
    "SAVINGS",
    "LOAN",
    "FINANCIAL",
    "MORTGAGE",
    "SERVICE",
    "SERVICES",
    "GROUP",
    "PARTNERS",
    "PARTNERSHIP",
    "ESTATE",
    "PROPERTIES",
    "REALTY",
    "ADJUSTMENT",
    "ENTERPRISES",
    "HOSPITAL",
    "MEDICAL",
    "HEALTH",
    "CENTER",
    "CLINIC",
    "PHYSICIANS",
    "SURGERY",
    "CARE",
    "UNIVERSITY",
    "COLLEGE",
    "SCHOOL",
    "AUTHORITY",
    "TRANSIT",
    "EDUCATION",
    "BOARD",
    "CAPITAL",
    "AGENCY",
    "HOLDINGS",
    "HOLDING",
    "VENTURES",
    "VENTURE",
    "MANAGEMENT",
    "ASSOCIATES",
    "ASSOCIATE",
    "SOLUTIONS",
    "LAW",
    "OFFICES",
    "FUND",
    "FOUNDATION",
    "CHURCH",
    "DIOCESE",
    "DISTRICT",
    "DEPARTMENT",
    "COMMISSION",
    "BUREAU",
    "ADMINISTRATOR",
    "RECEIVER",
    "MUTUAL",
    "INSURANCE",
}

# Multi-word markers that are organizations even when no legal suffix appears.
ORG_PHRASES = (
    "BLUE CROSS",
    "BLUE SHIELD",
    "STATE OF",
    "CITY OF",
    "COUNTY OF",
    "VILLAGE OF",
    "TOWNSHIP OF",
    "DEPARTMENT OF",
    "BOARD OF",
    "UNITED STATES",
    "ESTATE OF",
    "TRUST OF",
    "IN RE",
)

# Text that describes a role in a case caption rather than a party name.
ROLE_SUFFIXES = (
    "ET AL",
    "ETAL",
    "ET. AL.",
    "ET. AL",
    "ET., AL",
    ", ET AL",
    ", ETAL",
    "ET UX",
    "ET VIR",
    "ADMIN.",
    "ADMR.",
    "ADMINISTRATOR",
    "ETC.",
    "ETC",
    "CLERK OF COURTS",
    "RE'REPOSSESSION TITLE",
)

# Legal capacities that appear after a comma in transfer and court records.
CAPACITY_SUFFIXES = {
    "TRUSTEE",
    "SUCCESSOR TRUSTEE",
    "SUCC TRS",
    "TRS",
    "TR",
    "PRESIDENT",
    "VICE PRESIDENT",
    "VP",
    "SECRETARY",
    "TREASURER",
    "MANAGING MEMBER",
    "MEMBER",
    "MANAGER",
    "GENERAL PARTNER",
    "GP",
    "REGISTERED AGENT",
    "ATTORNEY",
    "ATTY",
    "ESQ",
    "ESQUIRE",
    "ATTORNEY IN FACT",
    "AIF",
}

_ALIAS_SPLIT = re.compile(r"\s+(?:AKA|A/K/A|FKA|F/K/A|DBA|D/B/A)\s+", re.IGNORECASE)
_CAPTION_SPLIT = re.compile(r"\s+(?:v\.?|vs\.?)\s+", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
_PUNCT_EDGE = re.compile(r"^[\s,;:.]+|[\s,;:.]+$")

# Names that describe a role or an unknown party rather than a person.
PLACEHOLDER_PARTS = {
    "UNKNOWN",
    "UNK",
    "NONE",
    "NULL",
    "N/A",
    "NA",
    "TBD",
    "OCCUPANT",
    "TENANT",
    "HEIRS",
    "ETAL",
}
PLACEHOLDER_PHRASES = {
    "JOHN DOE",
    "JANE DOE",
    "UNKNOWN SPOUSE",
    "UNKNOWN HEIRS",
    "ALL UNKNOWN HEIRS",
    "ALL OTHER PERSONS",
    "THE UNKNOWN HEIRS",
}


def is_placeholder(value: object) -> bool:
    """True for caption filler such as ``UNKNOWN SPOUSE`` or ``ET AL``."""
    text = clean_name(value).upper()
    if not text:
        return True
    if text in PLACEHOLDER_PHRASES or text.startswith("SEE PARCEL"):
        return True
    tokens = [token.strip(".,;:") for token in text.replace(",", " ").split()]
    if not tokens:
        return True
    return all(token in PLACEHOLDER_PARTS for token in tokens)


def clean_name(value: object) -> str:
    """Normalize whitespace and edge punctuation without changing the name."""
    if value is None:
        return ""
    text = _WHITESPACE.sub(" ", str(value)).strip()
    return _PUNCT_EDGE.sub("", text)


def _upper(value: object) -> str:
    return clean_name(value).upper()


def strip_role_suffixes(value: str) -> str:
    """Remove caption noise such as ``ET AL`` and ``ADMIN.`` from a party."""
    text = clean_name(value)
    changed = True
    while changed and text:
        changed = False
        upper = text.upper()
        for suffix in ROLE_SUFFIXES:
            if upper.endswith(suffix.upper()):
                text = clean_name(text[: -len(suffix)])
                changed = True
                break
        if not changed and upper.endswith(", ET AL."):
            text = clean_name(text[: -len(", ET AL.")])
            changed = True
        if not changed and "," in text:
            head, tail = text.rsplit(",", 1)
            if tail.strip().upper() in CAPACITY_SUFFIXES:
                text = clean_name(head)
                changed = True
    return text


def strip_generational_suffix(value: str) -> tuple[str, str | None]:
    """Return ``(name_without_suffix, suffix)`` for trailing JR/SR/II/III/IV."""
    text = clean_name(value)
    if not text:
        return "", None
    # Commas before a suffix are common: "SMITH, JOHN, JR".
    normalized = re.sub(r",\s*(JR|SR|II|III|IV|V)\.?$", r" \1", text, flags=re.IGNORECASE)
    tokens = normalized.split()
    if len(tokens) > 1 and tokens[-1].upper() in GENERATIONAL_SUFFIXES:
        suffix = tokens[-1].upper().rstrip(".")
        base = clean_name(" ".join(tokens[:-1]))
        # Put a comma back if the original was "LAST, FIRST, JR".
        if "," in text and "," not in base:
            head, rest = text.split(",", 1)
            rest = re.sub(r",?\s*(JR|SR|II|III|IV|V)\.?$", "", rest, flags=re.IGNORECASE)
            base = clean_name(f"{head}, {rest}")
        return base, suffix
    return text, None


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[\s,]+", _upper(value)) if token]


def is_organization(value: object) -> bool:
    """Return True when a party name describes an organization."""
    text = strip_role_suffixes(clean_name(value))
    if not text:
        return False
    upper = text.upper()

    # Comma-form people such as "CO, MARY" are common.  Treat a short
    # surname head as a person unless the legal suffix is on the name itself.
    head, _, tail = upper.partition(",")
    comma_person = bool(tail.strip()) and len(head.split()) <= 3

    tokens = _tokens(text)
    if not tokens:
        return False
    if any(token.rstrip(".") in {t.rstrip(".") for t in ORG_TOKENS} for token in tokens):
        # "CO, MARY" is the one important exception: CO is the surname.
        if comma_person and tokens[0].rstrip(".") == "CO":
            return False
        return True
    if any(phrase in upper for phrase in ORG_PHRASES):
        return True
    # "D/B/A" and "DBA" usually introduce a trade name.  Alias markers such as
    # AKA/FKA do not by themselves make a person an organization.
    if re.search(r"\b(?:D/B/A|DBA)\b", upper):
        return True
    return False


def parse_person(value: object) -> tuple[str, str, str, str | None] | None:
    """Return ``(last, first, middle, suffix)`` or None when not a person.

    Both ``LAST, FIRST MIDDLE`` and ``FIRST MIDDLE LAST`` are accepted.
    Generational suffixes are stripped before the surname is chosen.
    """
    text = strip_role_suffixes(clean_name(value))
    if not text:
        return None
    text, suffix = strip_generational_suffix(text)
    if not text:
        return None

    if "," in text:
        last_part, rest = text.split(",", 1)
        last = clean_name(last_part)
        rest_tokens = [token for token in rest.split() if token]
        if not last or not rest_tokens:
            return None
        first = rest_tokens[0]
        middle = " ".join(rest_tokens[1:])
        return last.upper(), first.upper(), middle.upper(), suffix

    tokens = [token for token in text.split() if token]
    if len(tokens) < 2:
        return None
    # If the string starts with a surname in a known "LAST FIRST" list there
    # is no reliable way to tell without a comma.  The data uses natural order
    # for un-comma'd names, so use the final token as the surname.
    last = tokens[-1]
    first = tokens[0]
    middle = " ".join(tokens[1:-1])
    return last.upper(), first.upper(), middle.upper(), suffix


def person_key(value: object) -> str | None:
    """Return ``owner|LAST, FIRST M`` or None when the name is not a person."""
    parsed = parse_person(value)
    if parsed is None:
        return None
    last, first, middle, _suffix = parsed
    if not last or not first:
        return None
    initial = middle[:1] if middle else ""
    name = f"{last}, {first}"
    if initial:
        name += f" {initial}"
    return f"owner|{name}"


class PersonIdentity(NamedTuple):
    """Name parts used to decide whether two records describe one person."""

    last: str
    first: str
    middle: str = ""
    suffix: str | None = None


def person_identity(value: object) -> PersonIdentity | None:
    """Parse a name into the parts used for identity checks."""
    parsed = parse_person(value)
    if parsed is None:
        return None
    last, first, middle, suffix = parsed
    if not last or not first:
        return None
    return PersonIdentity(last, first, middle, suffix)


def identities_match(left: PersonIdentity | None, right: PersonIdentity | None) -> bool:
    """True when two names are compatible identities.

    Surnames and first names must agree.  A middle initial is compared only
    when both records carry one.  Generational suffixes must agree when both
    are present; a missing suffix is treated as unknown, not as a mismatch.
    """
    if left is None or right is None:
        return False
    if left.last != right.last or left.first != right.first:
        return False
    left_mid = left.middle[:1].rstrip(".")
    right_mid = right.middle[:1].rstrip(".")
    if left_mid and right_mid and left_mid != right_mid:
        return False
    left_suffix = (left.suffix or "").rstrip(".").upper()
    right_suffix = (right.suffix or "").rstrip(".").upper()
    if left_suffix and right_suffix and left_suffix != right_suffix:
        return False
    return True


def docket_identity(value: object) -> PersonIdentity | None:
    """Parse a docket row name (``LAST FIRST MIDDLE [SUFFIX]``) into an identity.

    The Cuyahoga docket tables return names in natural order without commas,
    e.g. ``ROCCO JOHN C`` or ``SMITH JANE D JR``.
    """
    text = clean_name(value)
    if not text:
        return None
    parts = text.upper().split()
    if len(parts) < 2:
        return None
    suffix = None
    if parts[-1].rstrip(".") in GENERATIONAL_SUFFIXES:
        suffix = parts.pop()
    if len(parts) < 2:
        return None
    last = parts[0]
    first = parts[1]
    middle = " ".join(parts[2:]) if len(parts) > 2 else ""
    if not last or not first:
        return None
    return PersonIdentity(last, first, middle, suffix)


def name_from_node_key(node_key: object) -> str | None:
    """Turn ``owner|LAST, FIRST`` back into a parseable ``FIRST LAST`` name."""
    text = clean_name(node_key)
    if not text:
        return None
    if "|" in text:
        prefix, body = text.split("|", 1)
        if prefix.casefold() not in {"owner", "org"}:
            return None
        text = body
    if "," in text:
        last, rest = text.split(",", 1)
        return clean_name(f"{rest} {last}")
    return text


def organization_key(value: object) -> str | None:
    text = strip_role_suffixes(clean_name(value))
    if not text:
        return None
    return f"org|{text.upper()}"


def party_key(value: object) -> str | None:
    """Return a stable node key for exactly one party.

    A joint caption string such as ``JOHN SMITH & JANE DOE`` is ambiguous and
    returns None; callers must use :func:`split_parties` first.
    """
    text = strip_role_suffixes(clean_name(value))
    if not text:
        return None
    parties = split_parties(text)
    if len(parties) != 1:
        return None
    text = _split_alias(parties[0])
    if not text:
        return None
    if is_organization(text):
        return organization_key(text)
    return person_key(text)


def _split_alias(value: str) -> str:
    """Keep the legal name before AKA/FKA/DBA; aliases are not surnames."""
    parts = _ALIAS_SPLIT.split(value, maxsplit=1)
    return clean_name(parts[0]) if parts else clean_name(value)


def _looks_like_given_only(part: str) -> bool:
    """True for ``MARY`` / ``DAVID W``, i.e. a name missing its surname."""
    tokens = part.split()
    if not tokens:
        return False
    if len(tokens) == 1:
        return True
    # A trailing single letter is a middle initial, not a surname.
    return len(tokens) == 2 and len(tokens[-1].rstrip(".")) == 1


def _shared_surname(parts: list[str]) -> tuple[str | None, str | None]:
    """Find a surname shared by a caption's joint parties.

    ``SMITH, JOHN AND MARY`` shares the comma-form surname.  ``DAVID W &
    HEATHER WAGNER`` shares the natural-order surname.  Two full names such
    as ``FRAN HARBERT & MARK BOYNTON`` share nothing.
    """
    comma_parts = [part for part in parts if "," in part]
    if comma_parts:
        heads = {part.split(",", 1)[0].strip().upper() for part in comma_parts}
        if len(heads) == 1:
            return next(iter(heads)), "comma"

    candidates = [part for part in parts if not _looks_like_given_only(part)]
    if len(candidates) == 1:
        tokens = candidates[0].split()
        if len(tokens) >= 2:
            return tokens[-1], "natural"
    return None, None


def split_parties(value: object) -> list[str]:
    """Split a caption party field into individual people/organizations.

    ``SMITH AND JONES LLC`` stays one organization.  ``FRAN HARBERT & MARK
    BOYNTON`` becomes two people.  ``DAVID W & HEATHER WAGNER`` gives both
    people the shared surname.
    """
    text = strip_role_suffixes(clean_name(value))
    if not text:
        return []
    text = _split_alias(text)
    if not text:
        return []

    if is_organization(text):
        return [text]

    # Do not split "AND" inside an obvious legal name.
    if re.search(r"\s+(?:&|AND)\s+", text, re.IGNORECASE):
        raw_parts = [clean_name(part) for part in re.split(r"\s+(?:&|AND)\s+", text, flags=re.IGNORECASE) if clean_name(part)]
        if len(raw_parts) <= 1:
            return [text]
        # If any part still looks organizational, keep the whole string.
        if any(is_organization(part) for part in raw_parts):
            return [text]
        shared_last, mode = _shared_surname(raw_parts)
        if shared_last and mode:
            adjusted = []
            for part in raw_parts:
                if mode == "comma" and "," in part:
                    adjusted.append(part)
                elif mode == "comma" and _looks_like_given_only(part):
                    adjusted.append(f"{part} {shared_last}")
                elif mode == "natural" and _looks_like_given_only(part):
                    adjusted.append(f"{part} {shared_last}")
                else:
                    adjusted.append(part)
            raw_parts = adjusted
        return raw_parts

    return [text]


def caption_sides(caption: object) -> tuple[str, str] | None:
    """Split a case caption into ``(left, right)`` around v./vs."""
    text = clean_name(caption)
    if not text:
        return None
    match = _CAPTION_SPLIT.search(text)
    if not match:
        return None
    left = clean_name(text[: match.start()])
    right = clean_name(text[match.end() :])
    if not left or not right:
        return None
    return left, right


def case_parties(caption: object) -> list[str]:
    """Return every party named in a caption, preserving side order."""
    sides = caption_sides(caption)
    if sides is None:
        return []
    parties: list[str] = []
    for side in sides:
        parties.extend(split_parties(side))
    return parties


def parties_on_side(caption: object, side: str) -> list[str]:
    sides = caption_sides(caption)
    if sides is None:
        return []
    left, right = sides
    return split_parties(left if side == "left" else right)


def target_side(caption: object, target_key: str) -> str | None:
    """Return ``left`` or ``right`` when the target key appears on that side."""
    sides = caption_sides(caption)
    if sides is None:
        return None
    left, right = sides
    left_keys = {party_key(party) for party in split_parties(left)}
    right_keys = {party_key(party) for party in split_parties(right)}
    if target_key in left_keys:
        return "left"
    if target_key in right_keys:
        return "right"
    return None


def other_side_parties(caption: object, target_key: str) -> list[str]:
    """Return the parties on the opposite side of the target, or []."""
    side = target_side(caption, target_key)
    if side is None:
        return []
    sides = caption_sides(caption)
    if sides is None:
        return []
    return split_parties(sides[1] if side == "left" else sides[0])


def case_year(case_number: object) -> int | None:
    """Extract a four-digit year from ``CV-87-12345`` or ``2016ML29035``."""
    text = clean_name(case_number).upper()
    if not text:
        return None
    # A four-digit year may be followed by letters (2016ML29035) or a
    # separator (CV-2016-12345).  A two-digit suffix must be delimited.
    match = re.search(r"(?:^|[-_/ ])(\d{4})(?=\D|$)", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:^|[-_/ ])(\d{2})(?=\D|$)", text)
    if not match:
        return None
    value = int(match.group(1))
    if value < 30:
        return 2000 + value
    if value < 100:
        return 1900 + value
    return None


def parse_date_of_birth(value: object) -> date | None:
    """Parse the date formats used by the voter file without raising."""
    text = clean_name(value)
    if not text:
        return None
    formats = ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d/%m/%Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def age_at_case(dob: object, case_number: object, minimum: int = 18) -> bool | None:
    """Return False when the person was under ``minimum`` at the case year.

    ``None`` means the age cannot be checked because the DOB or case year is
    unavailable.  Callers should treat None as "unknown", not as True/False.
    """
    birth = parse_date_of_birth(dob)
    year = case_year(case_number)
    if birth is None or year is None:
        return None
    return (year - birth.year) >= minimum
