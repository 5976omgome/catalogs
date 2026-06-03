"""
Audit pipeline: per-artist classification for catalogue acquisitions.

Output is a 5-state STATUS plus a legacy CLEAN/FLAGGED Verdict for any
downstream consumer that hasn't migrated yet.

    KEEP             - every label is a name variant or neutral distributor
    DROP_MAJOR       - any major-family hit (Universal/Sony/Warner/BMG/Disney/etc.)
    DROP_LICENSED    - any exclusivity / licensed-to / distributed-by-major clause
    DROP_THIRDPARTY  - any third-party indie that is NOT a name variant
    REVIEW           - mixed signals: some platform shows a name variant, another
                       shows a non-variant indie. Surface to a human.

Hard-fail priority: MAJOR > LICENSED > THIRDPARTY > REVIEW > KEEP.

Old-catalog age and the AI bridge are INFORMATIONAL ONLY now. They never
gate the status. (The previous spec flagged pre-2005 artists; the new spec
treats deep catalogue as desirable for licensing deals.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from . import ai_bridge
from .config import OLD_CATALOG_CUTOFF_YEAR
from .labels import (
    LabelEvaluation,
    evaluate_label,
    find_licensing_clause,
    is_name_variant,
    match_major_family,
    normalize,
)
from .sources import deezer, discogs, itunes, wikipedia


# Hard-fail status precedence: a single MAJOR or LICENSED beats everything.
_PRIORITY = {
    "MAJOR": 4,
    "LICENSED": 3,
    "THIRDPARTY": 2,
    "VARIANT": 1,
    "DISTRIBUTOR": 1,
    "EMPTY": 0,
}


@dataclass
class ArtistAudit:
    """
    Full per-artist record. The new fields are `status`, `status_reason`,
    `label_evaluations`, `informational`. Legacy fields (verdict,
    flag_reasons, itunes_*) are preserved so the SSE event payloads and
    Excel writer continue to work.
    """
    artist: str

    # New richer status (the spec)
    status: str = "REVIEW"
    status_reason: str = ""
    label_evaluations: List[LabelEvaluation] = field(default_factory=list)
    informational: List[str] = field(default_factory=list)

    # Legacy
    verdict: str = "FLAGGED"  # CLEAN if status == KEEP, else FLAGGED
    flag_reasons: List[str] = field(default_factory=list)

    # Source snapshots (kept for the Excel sheet)
    itunes_owners: List[str] = field(default_factory=list)
    itunes_pline: str = ""
    itunes_licensee: str = ""
    deezer_labels: List[str] = field(default_factory=list)
    discogs_labels: List[str] = field(default_factory=list)
    wikipedia_labels: List[str] = field(default_factory=list)
    chartmetric_label: str = ""
    earliest_year: str = ""
    chartmetric_first_year: str = ""

    # Compatibility flag - kept so existing UI fields don't break.
    likely_self_imprint: bool = False
    ai_used: bool = False


def _earliest_year(*candidates: str) -> str:
    years = [c for c in candidates if c and len(c) >= 4 and c[:4].isdigit()]
    if not years:
        return ""
    return min(years, key=lambda y: int(y[:4]))[:4]


def _evaluate_collected(
    artist: str,
    pairs: List[tuple],  # (source, label) entries
) -> List[LabelEvaluation]:
    """Run evaluate_label() per (source, label) and drop EMPTY entries."""
    out: List[LabelEvaluation] = []
    for source, label in pairs:
        ev = evaluate_label(source, artist, label)
        if ev.status != "EMPTY":
            out.append(ev)
    return out


def _derive_status(evaluations: List[LabelEvaluation]) -> tuple[str, str]:
    """
    Reduce the per-label evaluations into the row-level status + reason.

    Rules (in priority order):
      1. Any MAJOR -> DROP_MAJOR
      2. Any LICENSED -> DROP_LICENSED
      3. Any THIRDPARTY -> DROP_THIRDPARTY (unless mixed with VARIANT, see 4)
      4. Mix of VARIANT and THIRDPARTY -> REVIEW
      5. Only VARIANT and/or DISTRIBUTOR -> KEEP
      6. No evaluations at all -> REVIEW (no evidence either way)
    """
    if not evaluations:
        return ("REVIEW", "no platform returned label data")

    # Highest-priority hit wins for the headline reason.
    by_pri = sorted(evaluations, key=lambda e: -_PRIORITY.get(e.status, 0))

    statuses = {ev.status for ev in evaluations}

    if "MAJOR" in statuses:
        first = next(e for e in by_pri if e.status == "MAJOR")
        return (
            "DROP_MAJOR",
            f"{first.source}: {first.label} -> {first.family} family ({first.matched_token})",
        )

    if "LICENSED" in statuses:
        first = next(e for e in by_pri if e.status == "LICENSED")
        return (
            "DROP_LICENSED",
            f"{first.source}: licensed to '{first.licensee}' on '{first.label}'",
        )

    has_third = "THIRDPARTY" in statuses
    has_variant = "VARIANT" in statuses
    has_distrib = "DISTRIBUTOR" in statuses

    # Chartmetric is the user's self-reported label field. It often differs
    # from what's on the actual streaming-service P-line. The user's stated
    # rule: "I need artists with matching P lines" — meaning the iTunes
    # P-line is the source of truth. So if iTunes says VARIANT but
    # Chartmetric is the ONLY source returning THIRDPARTY, we trust iTunes
    # and KEEP the row (with a note).
    if has_third and has_variant:
        third = [e for e in evaluations if e.status == "THIRDPARTY"]
        third_sources = {e.source for e in third}
        variant_has_itunes = any(
            e.status == "VARIANT" and e.source.startswith("iTunes")
            for e in evaluations
        )
        if (
            variant_has_itunes
            and third_sources == {"Chartmetric"}
        ):
            return (
                "KEEP",
                "iTunes P-line is name variant; Chartmetric label "
                f"'{third[0].label}' ignored (advisory only)",
            )
        return (
            "REVIEW",
            "mixed: name variant on one platform, third-party on "
            + ", ".join(sorted(third_sources)),
        )

    if has_third:
        third = next(e for e in evaluations if e.status == "THIRDPARTY")
        return (
            "DROP_THIRDPARTY",
            f"{third.source}: '{third.label}' is not a name variant of the artist",
        )

    if has_variant or has_distrib:
        # Distinguish for clearer messaging.
        if has_variant and has_distrib:
            return ("KEEP", "name variant + neutral distributor placeholders")
        if has_variant:
            return ("KEEP", "label is name variant of artist on every platform")
        return ("KEEP", "neutral distributor placeholders only")

    return ("REVIEW", "indeterminate label evidence")


def audit_artist(
    artist: str,
    chartmetric_label: str = "",
    chartmetric_first_year: str = "",
) -> ArtistAudit:
    """
    Run the full audit for one artist. Pulls iTunes, Deezer, Discogs, and
    consumes the Chartmetric self-reported label, then derives the status.
    """
    a = ArtistAudit(
        artist=artist,
        chartmetric_label=chartmetric_label,
        chartmetric_first_year=chartmetric_first_year,
    )

    # ---- 1. Pull from each platform ----
    it_releases = itunes.get_releases(artist, limit=5)
    if it_releases:
        latest = it_releases[0]
        a.itunes_owners = list(latest.get("owners", []))
        a.itunes_pline = latest.get("pline", "")
        a.itunes_licensee = latest.get("licensee", "")

    dz_releases = deezer.get_releases(artist, limit=3)
    a.deezer_labels = [
        r["label"] for r in dz_releases if r.get("label", "").strip()
    ]

    dc_releases = discogs.get_releases(artist, limit=3)
    a.discogs_labels = [
        r["label"] for r in dc_releases if r.get("label", "").strip()
    ]

    # Wikipedia / Wikidata: structured label data + parent-chain walk
    wiki_results = wikipedia.get_labels(artist)
    a.wikipedia_labels = [r["label"] for r in wiki_results if r.get("label")]

    # Surface deal history as informational notes when dates are available
    for wr in wiki_results:
        if wr.get("start_year") or wr.get("end_year"):
            period = ""
            if wr.get("start_year") and wr.get("end_year"):
                period = f"{wr['start_year']}–{wr['end_year']}"
            elif wr.get("start_year"):
                period = f"{wr['start_year']}–present"
            elif wr.get("end_year"):
                period = f"?–{wr['end_year']}"
            major_note = f" ({wr['major_via_chain']} family)" if wr.get("major_via_chain") else ""
            a.informational.append(
                f"WIKI_DEAL: {wr['label']}{major_note} [{period}]"
            )

    # ---- 2. Build (source, label) pairs ----
    #
    # iTunes gives us multiple owners across multiple releases, plus an
    # explicit licensee field that we evaluate independently because it
    # represents an exclusivity arrangement even when the surface label
    # looks like a self-imprint.
    pairs: List[tuple] = []

    for rel in it_releases:
        for owner in rel.get("owners", []):
            pairs.append(("iTunes", owner))
        # Build a synthetic "iTunes (licensee)" label evaluation for any
        # licensee text. This guarantees a major-family hit on the licensee
        # produces DROP_MAJOR, and an unrecognized licensee produces
        # DROP_LICENSED via the licensing-clause path further below.
        lic = (rel.get("licensee") or "").strip()
        if lic:
            pairs.append(("iTunes (licensee)", lic))
        # Also evaluate the raw P-line so a "distributed by ..." clause
        # buried inside the copyright text triggers DROP_LICENSED even when
        # the parsed owners look harmless.
        pline = (rel.get("pline") or "").strip()
        if pline:
            pairs.append(("iTunes (P-line)", pline))

    for label in a.deezer_labels:
        pairs.append(("Deezer", label))

    for label in a.discogs_labels:
        pairs.append(("Discogs", label))

    # Wikipedia/Wikidata labels. If the parent-chain walk detected a major
    # that our token list doesn't know about, we still want to flag it.
    # We handle this by adding the label string to pairs (which goes through
    # evaluate_label as normal), BUT we also check the chain result: if the
    # chain found a major parent and evaluate_label didn't catch it via
    # tokens alone, we inject a synthetic MAJOR evaluation directly.
    for wiki_rec in wiki_results:
        label = wiki_rec.get("label", "").strip()
        if not label:
            continue
        pairs.append(("Wikipedia", label))

    cm = (chartmetric_label or "").strip()
    if cm and cm.lower() != "unknown label":
        pairs.append(("Chartmetric", cm))

    # ---- 3. Evaluate each pair ----
    a.label_evaluations = _evaluate_collected(artist, pairs)

    # ---- 3b. Wikipedia parent-chain major detection ----
    # If Wikidata's parent-org chain found a major owner on any label that
    # evaluate_label() didn't already catch via our token list, inject a
    # synthetic MAJOR evaluation. This catches obscure imprints like
    # "Republic Records" -> Universal that might not be in MAJOR_FAMILIES.
    for wiki_rec in wiki_results:
        label = wiki_rec.get("label", "").strip()
        major_family = wiki_rec.get("major_via_chain")
        if not label or not major_family:
            continue
        # Check if we already have a MAJOR eval for this label from Wikipedia
        already_major = any(
            ev.source == "Wikipedia" and ev.label == label and ev.status == "MAJOR"
            for ev in a.label_evaluations
        )
        if already_major:
            continue
        # The parent chain found a major, but our token list didn't. Add it.
        a.label_evaluations.append(
            LabelEvaluation(
                source="Wikipedia",
                label=label,
                status="MAJOR",
                reason=f"{major_family} family (via Wikidata parent chain)",
                family=major_family,
                matched_token=f"parent:{wiki_rec.get('major_chain_qid', '')}",
            )
        )

    # ---- 4. Earliest year (informational) ----
    candidates = [chartmetric_first_year]
    candidates.extend(r.get("release_year", "") for r in it_releases)
    candidates.extend(r.get("release_year", "") for r in dz_releases)
    candidates.extend(r.get("release_year", "") for r in dc_releases)
    if not chartmetric_first_year:
        candidates.append(itunes.get_earliest_year(artist))
        candidates.append(deezer.get_earliest_year(artist))
        candidates.append(discogs.get_earliest_year(artist))
    a.earliest_year = _earliest_year(*candidates)

    if a.earliest_year and int(a.earliest_year) < OLD_CATALOG_CUTOFF_YEAR:
        # INFORMATIONAL ONLY. Old catalog is desirable for catalogue deals.
        a.informational.append(
            f"OLD_CATALOG: earliest release {a.earliest_year} (informational, does not flag)"
        )

    # ---- 5. Derive status ----
    a.status, a.status_reason = _derive_status(a.label_evaluations)

    # ---- 6. Optional AI commentary on the third-party-only edge case ----
    #
    # The previous version let the AI bridge flip a row from FLAGGED back
    # to CLEAN. New rule: it CANNOT. The bridge is only allowed to add an
    # informational note when it agrees the labels are equivalent. We never
    # promote a DROP_THIRDPARTY to KEEP via AI.
    if a.status == "DROP_THIRDPARTY":
        all_labels: List[str] = []
        all_labels.extend(a.itunes_owners)
        all_labels.extend(a.deezer_labels)
        all_labels.extend(a.discogs_labels)
        if cm:
            all_labels.append(cm)
        try:
            agreed = ai_bridge.bridge_diverges(artist, all_labels)
        except Exception:
            agreed = False
        a.ai_used = True
        if agreed:
            a.informational.append(
                "AI: bridge thinks labels could be name-variant equivalents "
                "(informational only - status not changed)"
            )

    # ---- 7. Legacy compatibility ----
    a.verdict = "CLEAN" if a.status == "KEEP" else "FLAGGED"
    a.flag_reasons = [
        f"{ev.source}: {ev.status} - {ev.reason}"
        for ev in a.label_evaluations
        if ev.status in ("MAJOR", "LICENSED", "THIRDPARTY")
    ]
    if a.status == "REVIEW" and not a.flag_reasons:
        a.flag_reasons = [a.status_reason]
    # likely_self_imprint stays False under the new rules - the variant
    # rule absorbs the "X Music" pattern as a legitimate own-imprint.
    a.likely_self_imprint = False

    return a
