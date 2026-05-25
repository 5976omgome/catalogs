"""Per-artist audit pipeline.

Strict mode: only artists whose label data unanimously points to fully
self-released, distributor-only, post-2005 catalogs are returned CLEAN.
Everything else is FLAGGED with a specific reason. We never drop rows.

Sources, in order of authority:
  1. Apple iTunes `copyright` field (the legal P-line). Ground truth.
  2. Deezer `label` (current streaming metadata cross-check)
  3. Discogs releases (historical catalog cross-check)
  4. The Chartmetric-supplied "Associated Labels" cell

Verdicts:
  CLEAN    -- iTunes P-line names ONLY the artist, OR a known distributor.
              No licensee anywhere. Deezer/Discogs match. Earliest release
              year >= 2005. No major / indie hits anywhere.
  FLAGGED  -- Anything else. The Flag column says exactly why.

AI bridge: when the rule engine produces ONLY 'DIVERGES' reasons (i.e. no
major / indie / licensed-to / self-imprint / old-catalog hits), the AI
bridge in app.ai is asked whether the divergent label strings really refer
to the same self-release entity. If yes, the verdict is upgraded to CLEAN.
The AI cannot override any other flag type.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ai
from .labels import (
    OLD_CATALOG_CUTOFF,
    classify_label,
    is_distributor,
    is_exact_artist_match,
    is_likely_self_imprint,
    is_self_released,
)
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
    plines: list[str]
    licensees: list[str]
    flag_reasons: list[str]
    ever_signed: bool
    has_licensing: bool
    likely_self_imprint: bool
    earliest_year: int | None
    verdict: str            # CLEAN | FLAGGED
    reason: str

    def to_row(self) -> dict:
        return {
            "itunes_pline": " || ".join(self.plines) or (
                "self-released" if self.itunes_releases else "not found"),
            "itunes_licensee": " | ".join(self.licensees),
            "itunes_owners": " | ".join(self.itunes_labels) or (
                "self-released" if self.itunes_releases else "not found"),
            "deezer_labels": " | ".join(self.deezer_labels) or (
                "self-released" if self.deezer_releases else "not found"),
            "discogs_labels": " | ".join(self.discogs_labels) or (
                "self-released" if self.discogs_releases else "not found"),
            "ever_signed": "YES" if self.ever_signed else "no",
            "has_licensing": "YES" if self.has_licensing else "no",
            "likely_self_imprint": "YES" if self.likely_self_imprint else "no",
            "earliest_year": str(self.earliest_year) if self.earliest_year else "",
            "flag": " / ".join(self.flag_reasons),
            "verdict": self.verdict,
            "ai_reason": self.reason,
        }


def _scan(source: str, releases: list[dict], artist: str,
          flag_reasons: list[str]) -> tuple[list[str], bool, bool]:
    """Classify every label in `releases`. Returns
    (unique_labels_found, any_signed, any_likely_self_imprint)."""
    found: list[str] = []
    signed = False
    self_imprint = False
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
        elif cat == "other":
            if is_exact_artist_match(artist, label):
                pass  # exact match, clean
            elif is_likely_self_imprint(artist, label):
                self_imprint = True
                flag_reasons.append(
                    f"SELF_IMPRINT ({source}): {label} [{title}]"
                )
            else:
                signed = True
                flag_reasons.append(f"DIVERGES ({source}): {label} [{title}]")
    return found, signed, self_imprint


def _scan_itunes(releases: list[dict], artist: str, flag_reasons: list[str]
                 ) -> tuple[list[str], list[str], list[str], bool, bool, bool]:
    """iTunes is the authority: each release has multiple owners + a
    licensee. Every owner is classified independently; any licensee is a
    hard flag.

    Returns (all_owners_seen, plines, licensees, ever_signed,
             has_licensing, any_self_imprint).
    """
    all_owners: list[str] = []
    plines: list[str] = []
    licensees_seen: list[str] = []
    signed = False
    has_licensing = False
    self_imprint = False

    for rel in releases:
        title = rel.get("title", "")
        pline = (rel.get("copyright") or "").strip()
        if pline and pline not in plines:
            plines.append(pline)

        for owner in rel.get("owners", []):
            if not owner:
                continue
            if owner not in all_owners:
                all_owners.append(owner)
            cat = classify_label(owner)
            if cat == "major":
                signed = True
                flag_reasons.append(f"MAJOR (Apple P-line): {owner} [{title}]")
            elif cat == "indie":
                signed = True
                flag_reasons.append(f"INDIE (Apple P-line): {owner} [{title}]")
            elif cat == "other":
                if is_exact_artist_match(artist, owner):
                    pass  # CLEAN candidate
                elif is_likely_self_imprint(artist, owner):
                    self_imprint = True
                    flag_reasons.append(
                        f"SELF_IMPRINT (Apple P-line): {owner} [{title}]"
                    )
                else:
                    signed = True
                    flag_reasons.append(
                        f"DIVERGES (Apple P-line): {owner} [{title}]"
                    )

        licensee = (rel.get("licensee") or "").strip()
        if licensee:
            has_licensing = True
            if licensee not in licensees_seen:
                licensees_seen.append(licensee)
            if licensee not in all_owners:
                all_owners.append(licensee)
            # Always a hard flag, regardless of who the licensee is.
            cat = classify_label(licensee)
            tag = cat.upper() if cat in ("major", "indie") else "LICENSED-TO"
            signed = True
            flag_reasons.append(
                f"{tag} (Apple P-line, licensed-to): {licensee} [{title}]"
            )

    return all_owners, plines, licensees_seen, signed, has_licensing, self_imprint


def _earliest_year(it_full_earliest: int | None,
                   dz_full_earliest: int | None,
                   dc_full_earliest: int | None,
                   chartmetric_first_year: int | None) -> int | None:
    """Determine the artist's earliest known release year.

    The Chartmetric "First Release Date" column is the most trusted
    source because Chartmetric has already matched the right artist;
    no namesake risk. We use that whenever it's present.

    The per-source helpers (iTunes / Deezer / Discogs) each do a STRICT
    name match before accepting a year, which keeps namesake artists from
    polluting the result. We use them only as fallbacks or to find a
    year EARLIER than what Chartmetric reports.
    """
    candidates = [v for v in (chartmetric_first_year, it_full_earliest,
                              dz_full_earliest, dc_full_earliest)
                  if isinstance(v, int) and v > 1900]
    return min(candidates) if candidates else None


def _decide_verdict(*, signed: bool, has_licensing: bool,
                    self_imprint: bool, earliest_year: int | None,
                    has_any_pline: bool, has_any_data: bool,
                    flag_reasons: list[str]
                    ) -> tuple[str, str]:
    """Apply the final rules. Returns (verdict, reason)."""
    if signed:
        # signed includes major/indie hits AND any licensing-to clause
        first = next((r for r in flag_reasons
                      if "MAJOR" in r or "INDIE" in r or "LICENSED" in r),
                     flag_reasons[0] if flag_reasons else "label deal")
        return "FLAGGED", f"Label evidence found: {first}"

    if has_licensing:
        return "FLAGGED", "P-line shows masters licensed to a third party."

    if self_imprint:
        return "FLAGGED", (
            "Looks like a self-imprint (artist name + suffix). "
            "Surfaced for manual review."
        )

    if not has_any_data:
        return "FLAGGED", "No data found in any source. Manual check required."

    if not has_any_pline:
        # We require positive evidence from Apple before declaring CLEAN.
        return "FLAGGED", "No Apple P-line available. Cannot verify ownership."

    if earliest_year is not None and earliest_year < OLD_CATALOG_CUTOFF:
        return "FLAGGED", (
            f"Catalog dates back to {earliest_year} "
            f"(earlier than {OLD_CATALOG_CUTOFF}). "
            "Likely posthumous or long-tenured independent."
        )

    return "CLEAN", (
        "All sources self-released or distributor-only; "
        "P-line names only the artist."
    )


def audit_artist(artist: str, chartmetric_label: str = "",
                 chartmetric_first_year: int | None = None) -> ArtistAudit:
    """Run a full audit. Pure function, safe to call from a worker thread.

    chartmetric_first_year, when provided, is treated as the most trusted
    source for the catalog-age check (we trust Chartmetric to have
    correctly matched the artist).
    """
    artist = artist.strip()
    chartmetric_label = (chartmetric_label or "").strip()

    if not artist:
        return ArtistAudit(
            artist=artist, chartmetric_label=chartmetric_label,
            itunes_releases=[], deezer_releases=[], discogs_releases=[],
            itunes_labels=[], deezer_labels=[], discogs_labels=[],
            plines=[], licensees=[],
            flag_reasons=["empty artist name"], ever_signed=False,
            has_licensing=False, likely_self_imprint=False,
            earliest_year=None, verdict="FLAGGED",
            reason="No artist name in input row.",
        )

    # ----- Source fetches -----
    it_releases = itunes.get_releases(artist)
    dz_releases = deezer.get_releases(artist)
    dc_releases = discogs.get_releases(artist)

    # Earliest-year lookups (each cached, so cheap on re-runs)
    it_earliest = itunes.get_earliest_year(artist)
    dz_earliest = deezer.get_earliest_year(artist)
    dc_earliest = discogs.get_earliest_year(artist)

    # ----- Rule scans -----
    flag_reasons: list[str] = []
    it_owners, plines, licensees, it_signed, has_licensing, it_imprint = \
        _scan_itunes(it_releases, artist, flag_reasons)
    dz_labels, dz_signed, dz_imprint = _scan(
        "Deezer", dz_releases, artist, flag_reasons)
    dc_labels, dc_signed, dc_imprint = _scan(
        "Discogs", dc_releases, artist, flag_reasons)

    # Chartmetric-supplied label is rated last
    cm_signed = False
    cm_imprint = False
    if chartmetric_label:
        cat = classify_label(chartmetric_label)
        if cat == "major":
            cm_signed = True
            flag_reasons.append(f"MAJOR (Chartmetric): {chartmetric_label}")
        elif cat == "indie":
            cm_signed = True
            flag_reasons.append(f"INDIE (Chartmetric): {chartmetric_label}")
        elif cat == "other":
            if is_exact_artist_match(artist, chartmetric_label):
                pass
            elif is_likely_self_imprint(artist, chartmetric_label):
                cm_imprint = True
                flag_reasons.append(
                    f"SELF_IMPRINT (Chartmetric): {chartmetric_label}"
                )
            else:
                cm_signed = True
                flag_reasons.append(
                    f"DIVERGES (Chartmetric): {chartmetric_label}"
                )

    ever_signed = it_signed or dz_signed or dc_signed or cm_signed
    self_imprint = it_imprint or dz_imprint or dc_imprint or cm_imprint

    earliest_year = _earliest_year(it_earliest, dz_earliest, dc_earliest,
                                   chartmetric_first_year)
    if earliest_year is not None and earliest_year < OLD_CATALOG_CUTOFF:
        flag_reasons.append(f"OLD_CATALOG: earliest release {earliest_year}")

    has_any_pline = bool(plines)
    has_any_data = bool(it_releases or dz_releases or dc_releases or
                        chartmetric_label)

    verdict, reason = _decide_verdict(
        signed=ever_signed,
        has_licensing=has_licensing,
        self_imprint=self_imprint,
        earliest_year=earliest_year,
        has_any_pline=has_any_pline,
        has_any_data=has_any_data,
        flag_reasons=flag_reasons,
    )

    # AI bridge: if the only reasons we flagged are DIVERGES-style label
    # name mismatches, ask the AI whether the divergent strings actually
    # all describe the same self-release entity (e.g. "X Records" vs
    # "X Recordings"). If yes, upgrade FLAGGED -> CLEAN. AI cannot
    # override MAJOR / INDIE / LICENSED-TO / SELF_IMPRINT / OLD_CATALOG.
    diverges_only = bool(flag_reasons) and all(
        r.startswith("DIVERGES (") for r in flag_reasons
    )
    bridged = False
    if (
        verdict == "FLAGGED"
        and diverges_only
        and not has_licensing
        and not self_imprint
        and (earliest_year is None or earliest_year >= OLD_CATALOG_CUTOFF)
    ):
        is_match, bridge_reason = ai.bridge_diverges(
            artist=artist,
            itunes=" | ".join(it_owners),
            deezer=" | ".join(dz_labels),
            discogs=" | ".join(dc_labels),
            chartmetric=chartmetric_label,
        )
        if is_match:
            verdict = "CLEAN"
            reason = (
                "Bridged divergent label strings to the same self-release "
                f"entity across sources. ({bridge_reason})"
            )
            bridged = True
        else:
            # Surface the bridge's negative reasoning alongside the original.
            reason = f"{reason} | bridge: {bridge_reason}"

    return ArtistAudit(
        artist=artist,
        chartmetric_label=chartmetric_label,
        itunes_releases=it_releases,
        deezer_releases=dz_releases,
        discogs_releases=dc_releases,
        itunes_labels=it_owners,
        deezer_labels=dz_labels,
        discogs_labels=dc_labels,
        plines=plines,
        licensees=licensees,
        flag_reasons=flag_reasons,
        ever_signed=ever_signed,
        has_licensing=has_licensing,
        likely_self_imprint=self_imprint,
        earliest_year=earliest_year,
        verdict=verdict,
        reason=reason,
    )
