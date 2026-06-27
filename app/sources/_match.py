"""Shared high-precision artist-name matcher.

WHY THIS EXISTS
---------------
The iTunes/Deezer sources matched an artist query against an API result using
loose substring containment on a space-stripped, normalized string, e.g.::

    an = re.sub(r"[^a-z0-9]", "", artist.lower())   # "lil baby" -> "lilbaby"
    if an in item_artist or item_artist in an: ...

That over-matches namesakes catastrophically. The query "Mike" matched 20
distinct artists on iTunes (Mike Posner, Mike WiLL Made-It, KB Mike, Pastor
Mike Jr., ...) and their unrelated copyright/P-lines were all blended into a
single ownership verdict — producing both false DROPs (a namesake on a major)
and false KEEPs (a self-released namesake while the real artist is signed).
Confirmed end-to-end: audit_artist("Mike") returned DROP_MAJOR citing
"Mike Posner appears courtesy of Arista Records" — a completely different artist.

For an ownership audit, PRECISION matters far more than recall: pulling the
wrong artist's data yields a wrong verdict, whereas pulling fewer-but-correct
releases (or none, which surfaces as REVIEW) is safe.

MATCHING RULE
-------------
A candidate name matches the query iff, after Unicode-diacritic stripping,
lower-casing, punctuation removal and tokenization:

  * the space-stripped "tight" forms are exactly equal, OR
  * the token SETS are equal (order-independent), with singular/plural
    tolerance on each token and an optional leading "the" dropped.

This accepts legitimate variants ("mike." == "Mike", "Tyler, The Creator" ==
"Tyler the Creator", "Beyoncé" == "Beyonce") while rejecting namesakes
("Mike" != "Mike Posner") and feature credits ("Drake" != "Drake & Future").
"""
import re
import unicodedata
from typing import List


def _strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokens(name: str) -> List[str]:
    """Normalized token list: diacritic-free, lowercase, alnum-only words."""
    if not name:
        return []
    cleaned = re.sub(r"[^a-z0-9 ]", " ", _strip_diacritics(name).lower())
    toks = cleaned.split()
    # Drop a single leading "the" (e.g., "The Weeknd" ~= "Weeknd")
    if len(toks) > 1 and toks[0] == "the":
        toks = toks[1:]
    return toks


def tight(name: str) -> str:
    """Space-stripped normalized form, e.g. 'Lil Baby' -> 'lilbaby'."""
    return "".join(tokens(name))


def _singular(tok: str) -> str:
    """Naive singularization for plural tolerance ('records' -> 'record')."""
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok


def _token_set(name: str) -> frozenset:
    return frozenset(_singular(t) for t in tokens(name))


def artist_matches(query: str, candidate: str) -> bool:
    """Return True iff `candidate` is the same artist as `query`.

    High precision: exact tight-equality or order-independent token-set
    equality (with plural/diacritic/leading-"the" tolerance). Loose substring
    containment is intentionally NOT accepted.
    """
    if not query or not candidate:
        return False

    qt, ct = tight(query), tight(candidate)
    if not qt or not ct:
        return False

    # Fast path: identical space-stripped forms.
    if qt == ct:
        return True

    # Order-independent token-set equality with plural tolerance.
    return _token_set(query) == _token_set(candidate)
