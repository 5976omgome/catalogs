"""Per-artist audit pipeline.

Combines Deezer + Discogs label data, runs rule-based classification,
then asks AI for a final verdict. Yields events for live UI streaming.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import ai
from .labels import classify_label, is_self_released
from .sources import deezer, discogs


@dataclass
class ArtistAudit:
    artist: str
    chartmetric_label: str
    deezer_labels: list[str]
    discogs_labels: list[str]
    deezer_releases: list[dict]
    discogs_releases: list[dict]
    flag_reasons: list[str]
    ever_signed: bool
    verdict: str   # CLEAN | CAUTION | FLAGGED
    reason: str

    def to_row(self) -> dict:
        return {
            "deezer_labels": " | ".join(self.deezer_labels) or (
                "self-released" if self.deezer_releases else "not found"),
            "discogs_labels": " | ".join(self.discogs_labels) or (
                "self-released" if self.discogs_releases else "not found"),
            "ever_signed": "YES" if self.ever_signed else "no",
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


def audit_artist(artist: str, chartmetric_label: str = "") -> ArtistAudit:
    """Run a full audit for a single artist. Pure function, safe to call
    from a worker thread."""
    artist = artist.strip()
    chartmetric_label = (chartmetric_label or "").strip()

    dz_releases = deezer.get_releases(artist) if artist else []
    dc_releases = discogs.get_releases(artist) if artist else []

    flag_reasons: list[str] = []
    dz_labels, dz_signed = _scan("Deezer", dz_releases, artist, flag_reasons)
    dc_labels, dc_signed = _scan("Discogs", dc_releases, artist, flag_reasons)

    # Also evaluate the Chartmetric-supplied label
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

    ever_signed = dz_signed or dc_signed or cm_signed

    verdict, reason = ai.get_verdict(
        artist=artist,
        chartmetric=chartmetric_label,
        deezer=" | ".join(dz_labels),
        discogs=" | ".join(dc_labels),
        rule_flag=" / ".join(flag_reasons),
    )

    return ArtistAudit(
        artist=artist,
        chartmetric_label=chartmetric_label,
        deezer_labels=dz_labels,
        discogs_labels=dc_labels,
        deezer_releases=dz_releases,
        discogs_releases=dc_releases,
        flag_reasons=flag_reasons,
        ever_signed=ever_signed,
        verdict=verdict,
        reason=reason,
    )
