"""Audit engine — produces KEEP / DROP_MAJOR / DROP_LICENSED / DROP_THIRDPARTY / REVIEW
for each artist by combining iTunes, Deezer, Discogs, and Chartmetric data.

Key design decisions:
- iTunes P-line is treated as ground truth (legal owner of the recording)
- Chartmetric is advisory — if iTunes confirms a clean variant but CM has
  a third-party name, we trust iTunes
- OLD_CATALOG (pre-2005) is informational only, does NOT flag
- AI bridge is called only on DIVERGES-only cases (can promote to KEEP)
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app import labels
from app.sources import itunes, deezer, discogs
from app import ai_bridge


@dataclass
class LabelEval:
    """One label string evaluated against the artist."""
    source: str          # "iTunes", "Deezer", "Discogs", "Chartmetric"
    label: str           # The raw label/P-line text
    classification: str  # "variant", "distributor", "major", "licensed", "thirdparty"
    title: str = ""      # Release title (when available)
    year: Optional[int] = None


@dataclass
class ArtistAudit:
    """Complete audit result for one artist."""
    artist: str
    status: str = "REVIEW"          # KEEP, DROP_MAJOR, DROP_LICENSED, DROP_THIRDPARTY, REVIEW
    status_reason: str = ""
    evaluations: List[LabelEval] = field(default_factory=list)
    earliest_year: Optional[int] = None
    ai_note: str = ""               # Informational AI bridge result


def audit_artist(
    artist: str,
    chartmetric_label: str = "",
    chartmetric_first_year: Optional[int] = None,
) -> ArtistAudit:
    """Run the full audit pipeline for one artist.

    1. Pull releases from iTunes, Deezer, Discogs
    2. Classify each label/P-line against the artist name
    3. Check Chartmetric's self-reported label
    4. Derive status based on priority rules
    5. Optionally call AI bridge for ambiguous cases
    """
    audit = ArtistAudit(artist=artist)
    evals: List[LabelEval] = []

    # --- Pull from all sources ---
    itunes_releases = itunes.get_releases(artist)
    deezer_releases = deezer.get_releases(artist)
    discogs_releases = discogs.get_releases(artist)

    # --- Classify each label ---
    for rel in itunes_releases:
        # Split the P-line owner into individual entities
        owners = labels.split_owners(rel.get("label", ""))
        for owner in owners:
            cls = labels.classify_label(artist, owner)
            evals.append(LabelEval(
                source="iTunes",
                label=owner,
                classification=cls,
                title=rel.get("title", ""),
                year=rel.get("year"),
            ))
        # Also check the raw copyright for licensing clauses
        raw = rel.get("copyright_raw", "")
        licensee = labels.find_licensing_clause(raw)
        if licensee:
            evals.append(LabelEval(
                source="iTunes",
                label=f"licensed to: {licensee}",
                classification="licensed",
                title=rel.get("title", ""),
                year=rel.get("year"),
            ))

    for rel in deezer_releases:
        cls = labels.classify_label(artist, rel.get("label", ""))
        evals.append(LabelEval(
            source="Deezer",
            label=rel.get("label", ""),
            classification=cls,
            title=rel.get("title", ""),
            year=rel.get("year"),
        ))

    for rel in discogs_releases:
        cls = labels.classify_label(artist, rel.get("label", ""))
        evals.append(LabelEval(
            source="Discogs",
            label=rel.get("label", ""),
            classification=cls,
            title=rel.get("title", ""),
            year=rel.get("year"),
        ))

    # --- Chartmetric self-reported label ---
    cm = (chartmetric_label or "").strip()
    if cm and cm.lower() not in ("unknown label", "unknown", ""):
        cls = labels.classify_label(artist, cm)
        evals.append(LabelEval(
            source="Chartmetric",
            label=cm,
            classification=cls,
        ))

    audit.evaluations = evals

    # --- Earliest year (informational) ---
    years = []
    if chartmetric_first_year:
        years.append(chartmetric_first_year)
    it_year = itunes.get_earliest_year(artist)
    if it_year:
        years.append(it_year)
    dz_year = deezer.get_earliest_year(artist)
    if dz_year:
        years.append(dz_year)
    dc_year = discogs.get_earliest_year(artist)
    if dc_year:
        years.append(dc_year)
    audit.earliest_year = min(years) if years else None

    # --- Derive status ---
    _derive_status(audit)

    return audit


def _derive_status(audit: ArtistAudit):
    """Determine KEEP/DROP/REVIEW from the evaluations list.

    Priority order:
    1. Any MAJOR → DROP_MAJOR
    2. Any LICENSED → DROP_LICENSED
    3. Any THIRDPARTY → depends on context (see below)
    4. All VARIANT/DISTRIBUTOR → KEEP
    5. Mixed or empty → REVIEW
    """
    evals = audit.evaluations

    if not evals:
        audit.status = "REVIEW"
        audit.status_reason = "No data from any source"
        return

    # 1. Any major hit → DROP_MAJOR (collect ALL contributing sources)
    majors = [e for e in evals if e.classification == "major"]
    if majors:
        audit.status = "DROP_MAJOR"
        details = "; ".join(f"{e.source}={e.label!r}" for e in majors[:5])
        audit.status_reason = f"Major-family token in: {details}"
        return

    # 2. Any licensed hit → DROP_LICENSED (collect ALL)
    licensed = [e for e in evals if e.classification == "licensed"]
    if licensed:
        audit.status = "DROP_LICENSED"
        details = "; ".join(f"{e.source}={e.label!r}" for e in licensed[:5])
        audit.status_reason = f"Exclusive/licensing clause in: {details}"
        return

    # 3. Check thirdparty hits
    thirdparty = [e for e in evals if e.classification == "thirdparty"]
    clean = [e for e in evals if e.classification in ("variant", "distributor")]

    if thirdparty:
        # Special case: if iTunes shows VARIANT but Chartmetric is the ONLY
        # thirdparty source, trust iTunes (P-line is ground truth)
        itunes_clean = all(
            e.classification in ("variant", "distributor")
            for e in evals if e.source == "iTunes"
        )
        itunes_has_data = any(e.source == "iTunes" for e in evals)
        cm_only_thirdparty = all(e.source == "Chartmetric" for e in thirdparty)

        if itunes_has_data and itunes_clean and cm_only_thirdparty:
            audit.status = "KEEP"
            audit.status_reason = (
                "iTunes confirms self-released. Chartmetric label is advisory."
            )
            audit.ai_note = "CM advisory override"
            return

        # If we have a mix of clean + thirdparty, try AI bridge
        if clean and thirdparty:
            # Collect labels by source for AI
            labels_by_source = {}
            for e in evals:
                if e.classification == "thirdparty":
                    labels_by_source.setdefault(e.source, []).append(e.label)

            ai_result = ai_bridge.bridge_check(audit.artist, labels_by_source)
            if ai_result:
                audit.status = "KEEP"
                audit.status_reason = "All sources confirmed as same entity"
                audit.ai_note = ai_result
                return

            # AI didn't confirm — if majority is thirdparty, DROP
            if len(thirdparty) > len(clean):
                details = "; ".join(f"{e.source}={e.label!r}" for e in thirdparty[:5])
                audit.status = "DROP_THIRDPARTY"
                audit.status_reason = f"Third-party labels in: {details}"
                return
            else:
                # Mixed — surface for manual review
                audit.status = "REVIEW"
                tp_sources = "; ".join(f"{e.source}={e.label!r}" for e in thirdparty[:3])
                audit.status_reason = f"Mixed signals. Third-party: {tp_sources}"
                return

        # All thirdparty, no clean
        details = "; ".join(f"{e.source}={e.label!r}" for e in thirdparty[:5])
        audit.status = "DROP_THIRDPARTY"
        audit.status_reason = f"Third-party labels in: {details}"
        return

    # 4. All clean (variant or distributor)
    if clean:
        audit.status = "KEEP"
        audit.status_reason = "All sources show artist name or known distributor"
        return

    # 5. Shouldn't reach here, but safety
    audit.status = "REVIEW"
    audit.status_reason = "Unable to determine status"
