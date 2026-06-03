"""Email scraper — finds contact emails from artist websites.

100% free, no API keys, no credit limits.
Strategy:
1. Fetch the artist's website homepage
2. Scan for mailto: links and email regex patterns
3. Also check /contact, /about, /booking pages
4. Filter out generic/spam emails, return best candidates

Uses shared Session for connection reuse.
"""
import re
import time
import threading
from typing import Optional, Dict, List
from urllib.parse import urlparse, urljoin

from app.sources._http import ai_session as _s
from app import cache

# Rate limit — be respectful to artist websites
_scrape_lock = threading.Lock()
_last_request_time = 0.0
_MIN_INTERVAL = 0.8  # Max ~1.2 req/sec (respectful but not glacial)


def _rate_limit():
    """Non-blocking rate limiter — computes wait, releases lock, then sleeps."""
    global _last_request_time
    wait = 0.0
    with _scrape_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
        _last_request_time = now + wait  # Reserve this slot
    if wait > 0:
        time.sleep(wait)


# Email regex — matches standard email patterns
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Emails to skip (generic, auto-generated, or service emails)
_SKIP_PATTERNS = {
    "noreply", "no-reply", "donotreply", "mailer-daemon",
    "postmaster", "webmaster", "hostmaster", "abuse",
    "support@wordpress", "support@squarespace", "support@wix",
    "example.com", "sentry.io", "github.com", "googlemail",
    "schema.org", "w3.org", "privacy@", "gdpr@",
}

# File extensions that definitely aren't contact pages
_SKIP_EXTENSIONS = {".png", ".jpg", ".gif", ".svg", ".css", ".js", ".woff", ".ico"}

# Contact page paths to try
_CONTACT_PATHS = ["/contact", "/about", "/booking", "/book", "/press", "/management"]


def _is_valid_email(email: str) -> bool:
    """Filter out junk emails."""
    email_lower = email.lower()
    # Skip if matches any bad pattern
    for pattern in _SKIP_PATTERNS:
        if pattern in email_lower:
            return False
    # Skip image/asset filenames that matched regex
    if any(email_lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return False
    # Must have reasonable length
    if len(email) < 6 or len(email) > 80:
        return False
    # Must have a real TLD (not .png.jpg etc)
    parts = email.split("@")
    if len(parts) != 2:
        return False
    domain = parts[1]
    if "." not in domain:
        return False
    # Skip if domain is a known non-contact domain
    skip_domains = {"facebook.com", "twitter.com", "instagram.com", "youtube.com",
                    "spotify.com", "apple.com", "google.com", "amazon.com"}
    if domain.lower() in skip_domains:
        return False
    return True


def _extract_emails_from_html(html: str) -> List[str]:
    """Extract emails from HTML content."""
    # Find mailto: links first (highest confidence)
    mailto_emails = re.findall(r"mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", html)

    # Then find all email patterns in text
    all_emails = _EMAIL_RE.findall(html)

    # Combine, deduplicate, prioritize mailto
    seen = set()
    result = []
    for email in mailto_emails + all_emails:
        email_clean = email.strip().lower().rstrip(".")
        if email_clean not in seen and _is_valid_email(email_clean):
            seen.add(email_clean)
            result.append(email_clean)

    return result[:5]  # max 5 emails


def _fetch_page(url: str) -> Optional[str]:
    """Fetch a single page, return HTML or None."""
    try:
        _rate_limit()
        r = _s.get(
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
            allow_redirects=True,
        )
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text[:100000]  # cap at 100KB to avoid huge pages
        return None
    except Exception:
        return None


def scrape_website_emails(website_url: str) -> Optional[Dict]:
    """Scrape emails from an artist's website.

    Checks homepage + common contact pages.

    Returns:
        {"emails": ["contact@artist.com"], "website": "https://artist.com", "source": "website"}
    or None if nothing found.
    """
    if not website_url:
        return None

    # Normalize URL
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    # Check cache
    cache_key = f"email_scrape:{website_url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    try:
        parsed = urlparse(website_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Skip social media domains
        skip_domains = {"instagram.com", "facebook.com", "twitter.com", "x.com",
                        "youtube.com", "tiktok.com", "soundcloud.com", "spotify.com",
                        "genius.com", "deezer.com", "apple.com", "linktr.ee",
                        "linktree.com", "distrokid.com", "tunecore.com"}
        domain = parsed.netloc.lower().lstrip("www.")
        if any(domain.endswith(s) or domain == s for s in skip_domains):
            cache.put(cache_key, {})
            return None

        all_emails = []

        # Fetch homepage
        html = _fetch_page(website_url)
        if html:
            emails = _extract_emails_from_html(html)
            all_emails.extend(emails)

        # If no emails on homepage, try contact pages
        if not all_emails:
            for path in _CONTACT_PATHS:
                contact_url = urljoin(base_url, path)
                html = _fetch_page(contact_url)
                if html:
                    emails = _extract_emails_from_html(html)
                    all_emails.extend(emails)
                    if all_emails:
                        break  # found some, stop checking more pages

        # Deduplicate
        seen = set()
        unique = []
        for e in all_emails:
            if e not in seen:
                seen.add(e)
                unique.append(e)

        if not unique:
            cache.put(cache_key, {})
            return None

        result = {
            "emails": unique[:3],
            "website": website_url,
            "source": "website",
        }

        print(f"[email] ✓ '{domain}' → {unique[:3]}", flush=True)
        cache.put(cache_key, result)
        return result

    except Exception as e:
        print(f"[email] Error scraping '{website_url}': {e}", flush=True)
        cache.put(cache_key, {})
        return None


def find_artist_website(instagram: Optional[str] = None) -> Optional[str]:
    """Try to derive an artist website URL from their Instagram handle.

    Many indie artists use their IG handle as their domain (handle.com).
    Only checks .com (by far most common). Caches failures to avoid repeated lookups.
    Returns URL string or None.
    """
    if not instagram:
        return None

    handle = instagram.strip().lstrip("@").lower()
    if not handle or len(handle) < 3 or len(handle) > 30:
        return None

    # Skip handles with numbers/underscores that are unlikely to be domains
    if handle.startswith("_") or handle.endswith("_"):
        return None

    # Check cache first (including negative cache)
    cache_key = f"website_lookup:{handle}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    # Only try .com — covers 90%+ of indie artist websites
    url = f"https://{handle}.com"
    try:
        _rate_limit()
        r = _s.head(url, timeout=3, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        if r.status_code == 200:
            cache.put(cache_key, url)
            return url
    except Exception:
        pass

    # Cache the miss so we don't re-check
    cache.put(cache_key, "")
    return None



def scrape_facebook_email(fb_handle: str) -> Optional[str]:
    """Scrape email from a Facebook page's About/info section.

    Many artist pages publicly display their contact email in the page info.
    We fetch the public Facebook page and scan for email patterns.

    Returns the first valid email found, or None.
    """
    if not fb_handle:
        return None

    # Normalize — could be a full URL or just a handle
    if fb_handle.startswith("http"):
        fb_url = fb_handle.rstrip("/")
    else:
        fb_url = f"https://www.facebook.com/{fb_handle.strip().lstrip('/')}"

    cache_key = f"fb_email:{fb_handle}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    try:
        # Try the About page (most likely to have email)
        about_url = fb_url + "/about"

        _rate_limit()
        html = None
        for url in [about_url, fb_url]:
            try:
                r = _s.get(
                    url,
                    timeout=8,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                    allow_redirects=True,
                )
                if r.status_code == 200:
                    html = r.text[:150000]
                    break
            except Exception:
                continue

        if not html:
            cache.put(cache_key, "")
            return None

        # Extract emails from the page
        emails = _extract_emails_from_html(html)

        # Filter out Facebook's own emails
        emails = [e for e in emails if "facebook.com" not in e and "fb.com" not in e]

        if emails:
            print(f"[email] ✓ FB '{fb_handle}' → {emails[0]}", flush=True)
            cache.put(cache_key, emails[0])
            return emails[0]

        cache.put(cache_key, "")
        return None

    except Exception as e:
        print(f"[email] FB scrape error '{fb_handle}': {e}", flush=True)
        cache.put(cache_key, "")
        return None


def scrape_youtube_description(artist_name: str) -> Optional[str]:
    """Scrape email from a YouTube channel's description/about section.

    YouTube hides the main contact email behind a CAPTCHA, but many artists
    also put their booking/management email in their channel description
    which IS publicly visible in the page source.

    Returns the first valid email found, or None.
    """
    if not artist_name:
        return None

    cache_key = f"yt_email:{artist_name.lower().strip()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    try:
        # Search YouTube for the artist's channel via their about page
        # We use YouTube's channel search URL which returns HTML with description
        search_query = artist_name.replace(" ", "+")
        search_url = f"https://www.youtube.com/results?search_query={search_query}&sp=EgIQAg%3D%3D"

        _rate_limit()
        r = _s.get(
            search_url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=True,
        )

        if r.status_code != 200:
            cache.put(cache_key, "")
            return None

        html = r.text[:200000]

        # YouTube embeds channel data in JSON within the page
        # Look for email patterns in the raw page source
        # The description text is in the initial data JSON
        emails = _extract_emails_from_html(html)

        # Filter out YouTube/Google emails
        emails = [e for e in emails if
                  "youtube.com" not in e and
                  "google.com" not in e and
                  "googleapis.com" not in e and
                  "ytimg.com" not in e]

        if emails:
            print(f"[email] ✓ YT '{artist_name}' → {emails[0]}", flush=True)
            cache.put(cache_key, emails[0])
            return emails[0]

        cache.put(cache_key, "")
        return None

    except Exception as e:
        print(f"[email] YT scrape error '{artist_name}': {e}", flush=True)
        cache.put(cache_key, "")
        return None
