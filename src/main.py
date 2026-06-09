"""
PagineGialle.it Business Scraper
Apify Actor - ayrtondavoli97/paginegialle-scraper
"""

import asyncio
import math
import re
import json
from urllib.parse import quote, urlencode

from curl_cffi.requests import AsyncSession
from apify import Actor
from .categories import CATEGORIES
from .utils import clean_phone, clean_text, extract_emails_from_text

BASE_URL = "https://www.paginegialle.it"
SEARCH_URL = f"{BASE_URL}/ricerca/{{what}}/{{where}}"
RESULTS_PER_PAGE = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.paginegialle.it/",
}

API_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        # Input params
        searches = inp.get("searches", [])
        max_results = inp.get("maxResults", 200)
        use_proxy = inp.get("useApifyProxy", True)
        proxy_country = inp.get("proxyCountry", "IT")
        only_with_phone = inp.get("onlyWithPhone", False)
        only_with_website = inp.get("onlyWithWebsite", False)
        only_with_email = inp.get("onlyWithEmail", False)

        if not searches:
            Actor.log.error("Input 'searches' is empty. Provide at least one {what, where} entry.")
            return

        # Proxy config
        proxy_config = None
        if use_proxy:
            proxy_config = await Actor.create_proxy_configuration(
                country_code=proxy_country,
            )

        dataset = await Actor.open_dataset()
        total_saved = 0

        async with AsyncSession(impersonate="chrome124") as session:
            for search_item in searches:
                what = search_item.get("what", "").strip()
                where = search_item.get("where", "").strip()

                if not what or not where:
                    Actor.log.warning(f"Skipping invalid search entry: {search_item}")
                    continue

                Actor.log.info(f"Searching: '{what}' in '{where}'")

                results = await scrape_search(
                    session=session,
                    what=what,
                    where=where,
                    max_results=max_results,
                    proxy_config=proxy_config,
                    only_with_phone=only_with_phone,
                    only_with_website=only_with_website,
                    only_with_email=only_with_email,
                )

                if results:
                    await dataset.push_data(results)
                    total_saved += len(results)
                    Actor.log.info(f"Saved {len(results)} results for '{what}' / '{where}'")

        Actor.log.info(f"Done. Total records saved: {total_saved}")


async def scrape_search(
    session,
    what: str,
    where: str,
    max_results: int,
    proxy_config,
    only_with_phone: bool,
    only_with_website: bool,
    only_with_email: bool,
) -> list[dict]:
    """Scrape all pages for a given what/where search."""

    results = []
    page = 1
    total_pages = 1
    seen_ids = set()

    what_enc = quote(what.lower().replace(" ", "-"))
    where_enc = quote(where.lower().replace(" ", "-"))

    while page <= total_pages and len(results) < max_results:
        url = build_search_url(what_enc, where_enc, page)
        proxy_url = await proxy_config.new_url() if proxy_config else None

        try:
            resp = await session.get(
                url,
                headers=API_HEADERS,
                proxy=proxy_url,
                timeout=30,
            )
        except Exception as e:
            Actor.log.warning(f"Request failed page {page}: {e}")
            break

        if resp.status_code != 200:
            Actor.log.warning(f"HTTP {resp.status_code} on page {page} - {url}")
            break

        data = parse_page(resp.text, what, where)

        if page == 1 and data.get("total_count", 0) > 0:
            total_pages = min(
                math.ceil(data["total_count"] / RESULTS_PER_PAGE),
                math.ceil(max_results / RESULTS_PER_PAGE),
            )
            Actor.log.info(f"Found ~{data['total_count']} total results ({total_pages} pages)")

        listings = data.get("listings", [])
        if not listings:
            Actor.log.info(f"No listings on page {page}, stopping.")
            break

        for item in listings:
            uid = item.get("id") or item.get("name", "") + item.get("address", "")
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            # Apply filters
            if only_with_phone and not item.get("phone"):
                continue
            if only_with_website and not item.get("website"):
                continue
            if only_with_email and not item.get("email"):
                continue

            results.append(item)
            if len(results) >= max_results:
                break

        Actor.log.info(f"Page {page}/{total_pages} scraped — {len(results)} results so far")
        page += 1
        await asyncio.sleep(0.8)

    return results


def build_search_url(what: str, where: str, page: int) -> str:
    """Build PagineGialle search URL with pagination."""
    base = f"{SEARCH_URL.format(what=what, where=where)}"
    params = {"output": "json"}
    if page > 1:
        params["pg"] = page
    return f"{base}?{urlencode(params)}"


def parse_page(html: str, what: str, where: str) -> dict:
    """
    Parse PagineGialle page response.
    Tries JSON endpoint first, falls back to HTML parsing.
    """
    # Try JSON parse
    try:
        data = json.loads(html)
        return parse_json_response(data, what, where)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract JSON from embedded script tags
    json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', html, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return parse_initial_state(data, what, where)
        except Exception:
            pass

    # Last resort: regex HTML parsing
    return parse_html_fallback(html, what, where)


def parse_json_response(data: dict, what: str, where: str) -> dict:
    """Parse direct JSON API response from PagineGialle."""
    listings = []
    raw_items = data.get("result", data.get("results", data.get("items", [])))
    total = data.get("total", data.get("count", len(raw_items)))

    for item in raw_items:
        listing = extract_listing_from_json(item, what, where)
        if listing:
            listings.append(listing)

    return {"listings": listings, "total_count": total}


def extract_listing_from_json(item: dict, what: str, where: str) -> dict | None:
    """Normalize a single JSON listing."""
    if not item:
        return None

    place = item.get("place", item.get("address", {}))
    if isinstance(place, str):
        address_str = place
        city = ""
        province = ""
        postal_code = ""
        lat = None
        lon = None
    else:
        address_str = clean_text(place.get("address", place.get("street", "")))
        city = clean_text(place.get("locality", place.get("city", where)))
        province = clean_text(place.get("region", place.get("province", "")))
        postal_code = clean_text(place.get("postal-code", place.get("postalCode", place.get("cap", ""))))
        lat = place.get("latitude", place.get("lat"))
        lon = place.get("longitude", place.get("lon", place.get("lng")))

    # Phone
    raw_phone = item.get("telephone", item.get("phone", item.get("tel", "")))
    phone = clean_phone(raw_phone) if raw_phone else ""

    # Rating
    rating = item.get("rating", item.get("score", item.get("stars")))
    try:
        rating = float(rating) if rating is not None else None
    except (ValueError, TypeError):
        rating = None

    # Social links
    social = item.get("social", {})
    if isinstance(social, list):
        social = {s.get("type", "unknown"): s.get("url", "") for s in social}

    return {
        "id": str(item.get("id", item.get("pgId", ""))),
        "name": clean_text(item.get("name", item.get("ragioneSociale", item.get("title", "")))),
        "subtitle": clean_text(item.get("subtitle", item.get("sottotitolo", ""))),
        "description": clean_text(item.get("description", item.get("descrizione", ""))),
        "category": clean_text(item.get("category", item.get("categoria", what))),
        "phone": phone,
        "email": clean_text(item.get("email", "")),
        "website": clean_text(item.get("website", item.get("sito", item.get("url", "")))),
        "address": address_str,
        "city": city,
        "province": province,
        "postalCode": postal_code,
        "latitude": float(lat) if lat else None,
        "longitude": float(lon) if lon else None,
        "rating": rating,
        "reviewCount": item.get("reviewCount", item.get("reviews", item.get("numRecensioni"))),
        "image": item.get("image", item.get("foto", item.get("logo", ""))),
        "facebook": social.get("facebook", ""),
        "instagram": social.get("instagram", ""),
        "searchWhat": what,
        "searchWhere": where,
        "sourceUrl": item.get("url", ""),
    }


def parse_initial_state(state: dict, what: str, where: str) -> dict:
    """Parse window.__INITIAL_STATE__ embedded JSON."""
    try:
        # Navigate common state tree paths
        search_data = (
            state.get("search", {})
            .get("results", state.get("listings", state.get("items", {})))
        )
        items = search_data.get("list", search_data.get("items", []))
        total = search_data.get("total", search_data.get("count", 0))

        listings = []
        for item in items:
            listing = extract_listing_from_json(item, what, where)
            if listing:
                listings.append(listing)

        return {"listings": listings, "total_count": total}
    except Exception:
        return {"listings": [], "total_count": 0}


def parse_html_fallback(html: str, what: str, where: str) -> dict:
    """Regex-based HTML fallback parser."""
    listings = []

    # Extract all business card blocks
    blocks = re.findall(
        r'<article[^>]*class="[^"]*listing[^"]*"[^>]*>(.*?)</article>',
        html, re.DOTALL | re.IGNORECASE
    )

    if not blocks:
        blocks = re.findall(
            r'<div[^>]*class="[^"]*result-item[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL | re.IGNORECASE
        )

    for block in blocks:
        name_m = re.search(r'<[^>]*class="[^"]*business-name[^"]*"[^>]*>(.*?)</[^>]+>', block, re.DOTALL)
        phone_m = re.search(r'<[^>]*class="[^"]*phone[^"]*"[^>]*>(.*?)</[^>]+>', block, re.DOTALL)
        addr_m = re.search(r'<[^>]*class="[^"]*address[^"]*"[^>]*>(.*?)</[^>]+>', block, re.DOTALL)
        web_m = re.search(r'href="(https?://(?!www\.paginegialle)[^"]+)"', block)
        cat_m = re.search(r'<[^>]*class="[^"]*category[^"]*"[^>]*>(.*?)</[^>]+>', block, re.DOTALL)
        email_m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', block)

        name = clean_text(re.sub(r'<[^>]+>', '', name_m.group(1))) if name_m else ""
        if not name:
            continue

        listings.append({
            "id": "",
            "name": name,
            "subtitle": "",
            "description": "",
            "category": clean_text(re.sub(r'<[^>]+>', '', cat_m.group(1))) if cat_m else what,
            "phone": clean_phone(re.sub(r'<[^>]+>', '', phone_m.group(1))) if phone_m else "",
            "email": email_m.group(0) if email_m else "",
            "website": web_m.group(1) if web_m else "",
            "address": clean_text(re.sub(r'<[^>]+>', '', addr_m.group(1))) if addr_m else "",
            "city": where,
            "province": "",
            "postalCode": "",
            "latitude": None,
            "longitude": None,
            "rating": None,
            "reviewCount": None,
            "image": "",
            "facebook": "",
            "instagram": "",
            "searchWhat": what,
            "searchWhere": where,
            "sourceUrl": "",
        })

    # Try to extract total count
    total_m = re.search(r'"total"\s*:\s*(\d+)', html)
    total = int(total_m.group(1)) if total_m else len(listings)

    return {"listings": listings, "total_count": total}
