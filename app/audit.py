"""Per-artist audit pipeline. Composes labels.classify_label across the
four sources (iTunes, Deezer, Discogs, Chartmetric) and produces a status
of KEEP / REVIEW / DROP_MAJOR / DROP_LICENSED / DROP_THIRDPARTY.

OLD_CATALOG (first release before EARLIEST_YEAR_CUTOFF) is INFORMATIONAL
under the current spec — it surfaces on the row but doesn't change the
status.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import ai_bridge, config, labels
from .sources import deezer, discogs, itunes


@dataclass
class LabelEvaluation:
    source: str            # "iTunes" | "Deezer" | "Discogs" | "Chartmetric"
    label: str
    classification: str    # "major" | "licensed" | "distributor" | "variant" | "thirdparty"
    title: Optional[str] = None
    year: Optional[int] = None


@dataclass
class ArtistAudit:
    artist: str
    status: str = "KEEP"
    status_reason: str = ""
    evaluations: List[LabelEvaluation] = field(default_factory=list)
    earliest_year: Optional[int] = None
    earliest_year_note: str = ""
    licensee: Optional[str] = None
    informational: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        # Backward-compat: KEEP -> CLEAN, anything else -> FLAGGED
        return "CLEAN" if self.status == "KEEP" else "FLAGGED"


def _evaluate_one(source: str, artist: str, label: str,
                  title: Optional[str] = None,
                  year: Optional[int] = None) -> Optional[LabelEvaluation]:
    if not label:
        return None
    cls = labels.classify_label(artist, label)
    return LabelEvaluation(
        source=source, label=label, classification=cls,
        title=title, year=year,
    )


def _derive_status(audit: ArtistAudit) -> None:
    """Walk evaluations in priority order and set status + reason."""
    evals = audit.evaluations

    # 1. Any major hit anywhere → DROP_MAJOR
    for e in evals:
        if e.classification == "major":
            audit.status = "DROP_MAJOR"
            audit.status_reason = (
                f"Major-family token in {e.source} label {e.label!r}"
            )
            return

    # 2. Any licensed hit anywhere → DROP_LICENSED
    for e in evals:
        if e.classification == "licensed":
            audit.status = "DROP_LICENSED"
            audit.status_reason = (
                f"Exclusive/licensing clause in {e.source} label {e.label!r}"
            )
            return

    # 3. Look at the spread of classifications across sources
    by_source: Dict[str, List[LabelEvaluation]] = {}
    for e in evals:
        by_source.setdefault(e.source, []).append(e)

    has_variant = any(e.classification == "variant" for e in evals)
    has_thirdparty = any(e.classification == "thirdparty" for e in evals)
    itunes_evs = by_source.get("iTunes", [])
    itunes_clean = bool(itunes_evs) and all(
        e.classification in ("variant", "distributor") for e in itunes_evs
    )

    # No data at all from any source → REVIEW
    if not evals:
        audit.status = "REVIEW"
        audit.status_reason = "No label data returned from any source"
        return

    # Strong rule: if iTunes (the P-line, legal owner of the recording) is
    # all-variant-or-distributor, we trust it, even if Chartmetric's self-
    # reported field has unrelated text.
    if itunes_clean and has_thirdparty:
        # downgrade Chartmetric-only thirdparty to advisory
        non_cm_third = [e for e in evals
                        if e.classification == "thirdparty" and e.source != "Chartmetric"]
        if not non_cm_third:
            audit.status = "KEEP"
            audit.status_reason = (
                "iTunes P-line confirms artist-owned imprint; "
                "Chartmetric label is advisory only"
            )
            return

    # All clean (variant / distributor only) → KEEP
    if all(e.classification in ("variant", "distributor") for e in evals):
        audit.status = "KEEP"
        if any(e.classification == "distributor" for e in evals):
            audit.status_reason = (
                "All sources show artist name, name variant, or DIY distributor"
            )
        else:
            audit.status_reason = "All sources show artist name or name variant"
        return

    # Mixed: at least one variant + at least one thirdparty → REVIEW
    if has_variant and has_thirdparty:
        audit.status = "REVIEW"
        bad = next(e for e in evals if e.classification == "thirdparty")
        audit.status_reason = (
            f"Mixed signals: some sources show name variant, "
            f"but {bad.source} shows {bad.label!r}"
        )
        return

    # Otherwise: pure thirdparty → DROP_THIRDPARTY
    if has_thirdparty:
        bad = next(e for e in evals if e.classification == "thirdparty")
        audit.status = "DROP_THIRDPARTY"
        audit.status_reason = (
            f"{bad.source} shows third-party label {bad.label!r} "
            f"(not a variant of the artist name)"
        )
        return

    # Fallback (shouldn't reach)
    audit.status = "REVIEW"
    audit.status_reason = "Unclassified mix of signals"


def audit_artist(artist: str, chartmetric_label: str = "",
                 chartmetric_first_year: Optional[int] = None,
                 enable_ai: bool = True) -> ArtistAudit:
    """Runs all sources and returns a populated ArtistAudit."""
    audit = ArtistAudit(artist=(artist or "").strip())
    if not audit.artist:
        audit.status = "REVIEW"
        audit.status_reason = "No artist name provided"
        return audit

    # ---- iTunes ----
    try:
        itunes_releases = itunes.get_releases(audit.artist)
    except Exception:
        itunes_releases = []
    for rel in itunes_releases[:5]:
        owners = rel.get("owners") or []
        for owner in owners:
            ev = _evaluate_one("iTunes", audit.artist, owner,
                               title=rel.get("collectionName"),
                               year=rel.get("releaseDate"))
            if ev:
                audit.evaluations.append(ev)
        # licensee captured separately
        if rel.get("licensee") and not audit.licensee:
            audit.licensee = str(rel["licensee"])
            # Add as a synthetic "licensed" evaluation so it gates the status
            audit.evaluations.append(LabelEvaluation(
                source="iTunes", label=str(rel["licensee"]),
                classification="licensed",
                title=rel.get("collectionName"),
                year=rel.get("releaseDate"),
            ))

    # ---- Deezer ----
    try:
        deezer_releases = deezer.get_releases(audit.artist)
    except Exception:
        deezer_releases = []
    for rel in deezer_releases[:3]:
        ev = _evaluate_one("Deezer", audit.artist, rel.get("label", ""),
                           title=rel.get("title"), year=rel.get("releaseDate"))
        if ev:
            audit.evaluations.append(ev)

    # ---- Discogs ----
    try:
        discogs_releases = discogs.get_releases(audit.artist)
    except Exception:
        discogs_releases = []
    for rel in discogs_releases[:3]:
        ev = _evaluate_one("Discogs", audit.artist, rel.get("label", ""),
                           title=rel.get("title"), year=rel.get("releaseDate"))
        if ev:
            audit.evaluations.append(ev)

    # ---- Chartmetric (advisory) ----
    cm = (chartmetric_label or "").strip()
    if cm and cm.lower() != "unknown label":
        ev = _evaluate_one("Chartmetric", audit.artist, cm)
        if ev:
            audit.evaluations.append(ev)

    # ---- Earliest year (informational) ----
    candidates = [chartmetric_first_year]
    for rels in (itunes_releases, deezer_releases, discogs_releases):
        for r in rels:
            y = r.get("releaseDate")
            if isinstance(y, int):
                candidates.append(y)
    years = [y for y in candidates if isinstance(y, int) and y > 1900]
    if years:
        audit.earliest_year = min(years)
        if audit.earliest_year < config.EARLIEST_YEAR_CUTOFF:
            audit.earliest_year_note = (
                f"OLD_CATALOG: earliest release {audit.earliest_year} "
                f"(< {config.EARLIEST_YEAR_CUTOFF}). Informational only."
            )

    # ---- Decide status ----
    _derive_status(audit)

    # ---- AI informational note (never gates) ----
    if enable_ai and audit.status in ("DROP_THIRDPARTY", "REVIEW"):
        try:
            note = ai_bridge.informational_note(
                audit.artist,
                [{"source": e.source, "label": e.label,
                  "classification": e.classification} for e in audit.evaluations],
            )
            if note:
                audit.informational.append(f"AI: {note}")
        except Exception:
            pass

    if audit.earliest_year_note:
        audit.informational.append(audit.earliest_year_note)

    return audit
