"""Per-artist audit pipeline.

Order of authority:
  1. Apple iTunes `copyright` (= the legal P-line, ground truth)
  2. Deezer `label` (current streaming metadata, cross-check)
  3. Discogs releases (historical catalog, cross-check)
  4. Chartmetric self-reported label (the input row)

The rule engine flags MAJOR / INDIE / DIVERGES / LICENSED on each source
independently and then the AI writes a final verdict using ALL of it,
including the raw P-line text so its reasoning is grounded in legal
language, not heuristics.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ai
from .labels import classify_label, is_self_released
from .sources import deezer, discogs, itunes


@dataclass
class ArtistAudit:
    artist: str
    chartmetric_label: str
    itunes_releases: list[dict]
    deezer_releases: list[dict]
    discogs_releases: list[dict]
    itunes_labels: list[str]
    deezer_labels: list[str]
    discogs_labels: list[str]
    plines: list[str]              # raw P-line strings, newest first
    licensees: list[str]           # any "licensed to" entities found
    flag_reasons: list[str]
    ever_signed: bool
    has_licensing: bool            # P-line contained "licensed to ..."
    verdict: str                   # CLEAN | CAUTION | FLAGGED
    reason: str

    def to_row(self) -> dict:
        return {
            "itunes_pline": " || ".join(self.plines) or (
                "self-released" if self.itunes_releases else "not found"),
            "itunes_licensee": " | ".join(self.licensees),
            "itunes_labels": " | ".join(self.itunes_labels) or (
                "self-released" if self.itunes_releases else "not found"),
            "deezer_labels": " | ".join(self.deezer_labels) or (
                "self-released" if self.deezer_releases else "not found"),
            "discogs_labels": " | ".join(self.discogs_labels) or (
                "self-released" if self.discogs_releases else "not found"),
            "ever_signed": "YES" if self.ever_signed else "no",
            "has_licensing": "YES" if self.has_licensing else "no",
            "flag": " / ".join(self.flag_reasons),
            "verdict": self.verdict,
            "ai_reason": self.reason,
        }


def _scan(source: str, releases: list[dict], artist: str,
          flag_reasons: list[str]) -> tuple[list[str], bool]:
    """Run rule-based classification on a list of releases.
    Returns (unique labels found, whether any release was non-self-release).
    """
    found: list[str] = []
    signed = False
    for rel in releases:
        label = (rel.get("label") or "").strip()
        if not label:
            continue
        if label not in found:
            found.append(label)
        cat = classify_label(label)
        title = rel.get("title", "")
        if cat == "major":
            signed = True
            flag_reasons.append(f"MAJOR ({source}): {label} [{title}]")
        elif cat == "indie":
            signed = True
            flag_reasons.append(f"INDIE ({source}): {label} [{title}]")
        elif cat == "other" and not is_self_released(artist, label):
            signed = True
            flag_reasons.append(f"DIVERGES ({source}): {label} [{title}]")
    return found, signed


def _scan_itunes(releases: list[dict], artist: str,
                 flag_reasons: list[str]
                 ) -> tuple[list[str], list[str], list[str], bool, bool]:
    """Itunes is special: each release has multiple owners + a licensee.
    EVERY owner gets classified independently, plus the licensee.

    Returns (all_labels_found, plines, licensees, signed, has_licensing).
    """
    all_labels: list[str] = []
    plines: list[str] = []
    licensees_seen: list[str] = []
    signed = False
    has_licensing = False

    for rel in releases:
        title = rel.get("title", "")
        pline = (rel.get("copyright") or "").strip()
        if pline and pline not in plines:
            plines.append(pline)

        # Each owner string is checked independently.
        for owner in rel.get("owners", []):
            if not owner:
                continue
            if owner not in all_labels:
                all_labels.append(owner)
            cat = classify_label(owner)
            if cat == "major":
                signed = True
                flag_reasons.append(f"MAJOR (Apple P-line): {owner} [{title}]")
            elif cat == "indie":
                signed = True
                flag_reasons.append(f"INDIE (Apple P-line): {owner} [{title}]")
            elif cat == "other" and not is_self_released(artist, owner):
                signed = True
                flag_reasons.append(f"DIVERGES (Apple P-line): {owner} [{title}]")

        licensee = (rel.get("licensee") or "").strip()
        if licensee:
            has_licensing = True
            if licensee not in licensees_seen:
                licensees_seen.append(licensee)
            if licensee not in all_labels:
                all_labels.append(licensee)
            cat = classify_label(licensee)
            # ANY licensing-to clause is a hard flag for catalog acquisition
            # because it means the masters are controlled by the licensee.
            tag = cat.upper() if cat in ("major", "indie") else "LICENSED-TO"
            signed = True
            flag_reasons.append(
                f"{tag} (Apple P-line, licensed-to): {licensee} [{title}]"
            )

    return all_labels, plines, licensees_seen, signed, has_licensing


def audit_artist(artist: str, chartmetric_label: str = "") -> ArtistAudit:
    """Run a full audit for a single artist. Pure function, safe to call
    from a worker thread."""
    artist = artist.strip()
    chartmetric_label = (chartmetric_label or "").strip()

    # Authoritative source first: the P-line from Apple.
    it_releases = itunes.get_releases(artist) if artist else []
    dz_releases = deezer.get_releases(artist) if artist else []
    dc_releases = discogs.get_releases(artist) if artist else []

    flag_reasons: list[str] = []
    it_labels, plines, licensees, it_signed, has_licensing = _scan_itunes(
        it_releases, artist, flag_reasons)
    dz_labels, dz_signed = _scan("Deezer", dz_releases, artist, flag_reasons)
    dc_labels, dc_signed = _scan("Discogs", dc_releases, artist, flag_reasons)

    # Also evaluate the Chartmetric-supplied label (lowest weight)
    cm_signed = False
    if chartmetric_label:
        cat = classify_label(chartmetric_label)
        if cat == "major":
            cm_signed = True
            flag_reasons.append(f"MAJOR (Chartmetric): {chartmetric_label}")
        elif cat == "indie":
            cm_signed = True
            flag_reasons.append(f"INDIE (Chartmetric): {chartmetric_label}")
        elif cat == "other" and not is_self_released(artist, chartmetric_label):
            cm_signed = True
            flag_reasons.append(f"DIVERGES (Chartmetric): {chartmetric_label}")

    ever_signed = it_signed or dz_signed or dc_signed or cm_signed

    verdict, reason = ai.get_verdict(
        artist=artist,
        chartmetric=chartmetric_label,
        plines=plines,
        licensees=licensees,
        deezer=" | ".join(dz_labels),
        discogs=" | ".join(dc_labels),
        rule_flag=" / ".join(flag_reasons),
    )

    return ArtistAudit(
        artist=artist,
        chartmetric_label=chartmetric_label,
        itunes_releases=it_releases,
        deezer_releases=dz_releases,
        discogs_releases=dc_releases,
        itunes_labels=it_labels,
        deezer_labels=dz_labels,
        discogs_labels=dc_labels,
        plines=plines,
        licensees=licensees,
        flag_reasons=flag_reasons,
        ever_signed=ever_signed,
        has_licensing=has_licensing,
        verdict=verdict,
        reason=reason,
    )
