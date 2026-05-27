"""Strict audit pipeline. CLEAN vs FLAGGED only - no caution bucket."""
from dataclasses import dataclass, field
from typing import List

from . import ai_bridge
from .config import OLD_CATALOG_CUTOFF_YEAR
from .labels import (
    classify_label, find_licensee, is_distributor,
    is_likely_self_imprint, is_self_released, normalize,
)
from .sources import deezer, discogs, itunes


@dataclass
class ArtistAudit:
    artist: str
    verdict: str = "FLAGGED"  # CLEAN | FLAGGED
    flag_reasons: List[str] = field(default_factory=list)
    itunes_owners: List[str] = field(default_factory=list)
    itunes_pline: str = ""
    itunes_licensee: str = ""
    deezer_labels: List[str] = field(default_factory=list)
    discogs_labels: List[str] = field(default_factory=list)
    chartmetric_label: str = ""
    earliest_year: str = ""
    chartmetric_first_year: str = ""
    likely_self_imprint: bool = False
    ai_used: bool = False


def _earliest_year(*candidates: str) -> str:
    """Return the smallest valid year string from candidates."""
    years = [c for c in candidates if c and len(c) >= 4 and c[:4].isdigit()]
    if not years:
        return ""
    return min(years, key=lambda y: int(y[:4]))[:4]


def _scan_label(source: str, artist: str, label: str, audit: ArtistAudit) -> bool:
    """
    Scan a single label string. Returns True if it triggered any flag.
    Mutates audit.flag_reasons.
    """
    if not label:
        return False
    cat = classify_label(label)
    if cat == "major":
        audit.flag_reasons.append(f"MAJOR ({source}): {label}")
        return True
    if cat == "indie":
        audit.flag_reasons.append(f"INDIE ({source}): {label}")
        return True
    if cat == "distributor":
        return False
    # other
    licensee = find_licensee(label)
    if licensee:
        audit.flag_reasons.append(f"LICENSED-TO ({source}): {licensee}")
        return True
    if is_likely_self_imprint(artist, label):
        audit.likely_self_imprint = True
        audit.flag_reasons.append(f"SELF_IMPRINT ({source}): {label}")
        return True
    if not is_self_released(artist, label):
        audit.flag_reasons.append(f"DIVERGES ({source}): {label}")
        return True
    return False


def audit_artist(
    artist: str,
    chartmetric_label: str = "",
    chartmetric_first_year: str = "",
) -> ArtistAudit:
    a = ArtistAudit(artist=artist, chartmetric_label=chartmetric_label,
                    chartmetric_first_year=chartmetric_first_year)

    # --- iTunes (P-line authority) ---
    it_releases = itunes.get_releases(artist, limit=5)
    if it_releases:
        # use most recent for primary owners/pline
        latest = it_releases[0]
        a.itunes_owners = latest.get("owners", [])
        a.itunes_pline = latest.get("pline", "")
        a.itunes_licensee = latest.get("licensee", "")
        # Scan every owner across all returned releases
        for rel in it_releases:
            for owner in rel.get("owners", []):
                _scan_label("iTunes", artist, owner, a)
            if rel.get("licensee"):
                # licensee is itself a label - classify it
                lic = rel["licensee"]
                cat = classify_label(lic)
                if cat == "major":
                    a.flag_reasons.append(f"LICENSED-TO-MAJOR (iTunes): {lic}")
                elif cat == "indie":
                    a.flag_reasons.append(f"LICENSED-TO-INDIE (iTunes): {lic}")
                else:
                    a.flag_reasons.append(f"LICENSED-TO (iTunes): {lic}")

    # --- Deezer ---
    dz_releases = deezer.get_releases(artist, limit=3)
    for rel in dz_releases:
        label = rel.get("label", "")
        if label:
            a.deezer_labels.append(label)
            _scan_label("Deezer", artist, label, a)

    # --- Discogs ---
    dc_releases = discogs.get_releases(artist, limit=3)
    for rel in dc_releases:
        label = rel.get("label", "")
        if label:
            a.discogs_labels.append(label)
            _scan_label("Discogs", artist, label, a)

    # --- Chartmetric self-reported label ---
    if chartmetric_label and chartmetric_label.strip().lower() not in ("", "unknown label"):
        _scan_label("Chartmetric", artist, chartmetric_label.strip(), a)

    # --- Earliest year ---
    candidates = [chartmetric_first_year]
    candidates.extend(r.get("release_year", "") for r in it_releases)
    candidates.extend(r.get("release_year", "") for r in dz_releases)
    candidates.extend(r.get("release_year", "") for r in dc_releases)
    # If chartmetric didn't supply, fall back to per-source earliest scans
    if not chartmetric_first_year:
        candidates.append(itunes.get_earliest_year(artist))
        candidates.append(deezer.get_earliest_year(artist))
        candidates.append(discogs.get_earliest_year(artist))
    a.earliest_year = _earliest_year(*candidates)

    if a.earliest_year and int(a.earliest_year) < OLD_CATALOG_CUTOFF_YEAR:
        a.flag_reasons.append(
            f"OLD_CATALOG: earliest release {a.earliest_year}"
        )

    # --- Decide verdict ---
    if not a.flag_reasons:
        a.verdict = "CLEAN"
        return a

    # AI bridge: only if EVERY flag is a DIVERGES flag
    diverges_only = all(r.startswith("DIVERGES") for r in a.flag_reasons)
    if diverges_only:
        all_labels = []
        all_labels.extend(a.itunes_owners)
        all_labels.extend(a.deezer_labels)
        all_labels.extend(a.discogs_labels)
        if chartmetric_label:
            all_labels.append(chartmetric_label)
        a.ai_used = True
        if ai_bridge.bridge_diverges(artist, all_labels):
            a.verdict = "CLEAN"
            a.flag_reasons.append("AI: bridged whitespace/punct differences")
            return a

    a.verdict = "FLAGGED"
    return a
