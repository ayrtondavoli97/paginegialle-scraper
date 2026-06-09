"""Utility helpers for PagineGialle scraper."""

import re
import html


def clean_text(text: str | None) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_phone(phone: str | None) -> str:
    """Normalize Italian phone number."""
    if not phone:
        return ""
    phone = clean_text(phone)
    # Keep only digits, spaces, +, -, ()
    phone = re.sub(r'[^\d\s\+\-\(\)]', '', phone)
    phone = re.sub(r'\s+', ' ', phone).strip()
    return phone


def extract_emails_from_text(text: str) -> list[str]:
    """Extract all email addresses from a string."""
    if not text:
        return []
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))


def normalize_search_term(term: str) -> str:
    """Convert a free-text category to PagineGialle URL slug."""
    term = term.lower().strip()
    # Replace spaces and common separators with hyphens
    term = re.sub(r'[\s_/]+', '-', term)
    # Remove characters not suitable for URL slug
    term = re.sub(r'[^\w\-]', '', term)
    # Collapse multiple hyphens
    term = re.sub(r'-+', '-', term)
    return term.strip('-')


def build_pg_url(what: str, where: str, page: int = 1) -> str:
    """Build a PagineGialle search URL."""
    from urllib.parse import quote
    what_slug = normalize_search_term(what)
    where_slug = normalize_search_term(where)
    base = f"https://www.paginegialle.it/ricerca/{quote(what_slug)}/{quote(where_slug)}"
    params = "?output=json"
    if page > 1:
        params += f"&pg={page}"
    return base + params
