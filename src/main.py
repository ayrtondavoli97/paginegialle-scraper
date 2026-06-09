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
RESULTS_PER_PAGE = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.paginegialle.it/",
    "Cache-Control": "no-cache",
}


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

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

        # Build proxy URL string once
        proxy_url = None
        if use_proxy:
            proxy_cfg = await Actor.create_proxy_configuration(
                country_code=proxy_country,
            )
            proxy_url = await proxy_cfg.new_url()
            Actor.log.info(f"Using proxy: {proxy_url.split('@')[-1] if proxy_url else 'none'}")

        dataset = await Actor.open_dataset()
        total_saved = 0

        for search_item in searches:
            what = search_item.get("what", "").strip()
            where = search_item.get("where", "").strip()

            if not what or not where:
                Actor.log.warning(f"Skipping invalid search entry: {search_item}")
                continue

            Actor.log.info(f"Searching: '{what}' in '{where}'")

            results = await scrape_search(
                what=what,
                where=where,
                max_results=max_results,
                proxy_url=proxy_url,
                only_with_phone=only_with_phone,
                only_with_website=only_with_website,
                only_with_email=only_with_email,
            )

            if results:
                await dataset.push_data(results)
                total_saved += len(results)
                Actor.log.info(f"Saved {len(results)} results for '{what}' / '{where}'")
            else:
                Actor.log.warning(f"No results for '{what}' / '{where}'")

        Actor.log.info(f"Done. Total records saved: {total_saved}")


async def scrape_search(
    what: str,
    where: str,
    max_results: int,
    proxy_url: str | None,
    only_with_phone: bool,
    only_with_website: bool,
    only_with_email: bool,
) -> list[dict]:
    """Scrape all pages for a given what/where search."""

    results = []
    page = 1
    total_pages = 1
    seen_ids = set()

    what_slug = normalize_slug(what)
    where_slug = normalize_slug(where)

    # Build proxies dict for curl_cffi
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

    async with AsyncSession(impersonate="chrome124", proxies=proxies) as session:
        # First: visit homepage to get cookies
        try:
            await session.get(BASE_URL, headers=HEADERS, timeout=15)
            await asyncio.sleep(0.5)
        except Exception as e:
            Actor.log.warning(f"Homepage warmup failed (non-fatal): {e}")

        while page <= total_pages and len(results) < max_results:
            url = build_search_url(what_slug, where_slug, page)
            Actor.log.info(f"Fetching page {page}: {url}")

            try:
                resp = await session.get(
                    url,
                    headers={
                        **HEADERS,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                    timeout=30,
                    allow_redirects=True,
                )
            except Exception as e:
                Actor.log.warning(f"Request failed page {page}: {e}")
                break

            Actor.log.info(f"Response: HTTP {resp.status_code}, {len(resp.text)} chars")

            if resp.status_code == 429:
                Actor.log.warning("Rate limited (429). Waiting 5s...")
                await asyncio.sleep(5)
                continue

            if resp.status_code != 200:
                Actor.log.warning(f"HTTP {resp.status_code} on page {page}")
                break

            data = parse_page(resp.text, what, where)

            if page == 1:
                total_count = data.get("total_count", 0)
                if total_count > 0:
                    total_pages = min(
                        math.ceil(total_count / RESULTS_PER_PAGE),
                        math.ceil(max_results / RESULTS_PER_PAGE),
                    )
                    Actor.log.info(f"Total: ~{total_count} results ({total_pages} pages)")
                else:
                    Actor.log.info("No total count found, will scrape until empty")
                    total_pages = math.ceil(max_results / RESULTS_PER_PAGE)

            listings = data.get("listings", [])
            if not listings:
                Actor.log.info(f"No listings on page {page}, stopping.")
                break

            for item in listings:
                uid = item.get("id") or (item.get("name", "") + item.get("address", ""))
                if uid and uid in seen_ids:
                    continue
                if uid:
                    seen_ids.add(uid)

                if only_with_phone and not item.get("phone"):
                    continue
                if only_with_website and not item.get("website"):
                    continue
                if only_with_email and not item.get("email"):
                    continue

                results.append(item)
                if len(results) >= max_results:
                    break

            Actor.log.info(f"Page {page}/{total_pages} done — {len(results)} total results")
            page += 1
            await asyncio.sleep(1.0)

    return results


def normalize_slug(text: str) -> str:
    """Convert text to PagineGialle URL slug."""
    text = text.lower().strip()
    text = re.sub(r"[\s_/]+", "-", text)
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def build_search_url(what_slug: str, where_slug: str, page: int) -> str:
    """Build PagineGialle search URL."""
    base = f"{BASE_URL}/ricerca/{what_slug}/{where_slug}"
    params: dict = {}
    if page > 1:
        params["pg"] = page
    if params:
        return f"{base}?{urlencode(params)}"
    return base


def parse_page(html: str, what: str, where: str) -> dict:
    """Parse PagineGialle page — tries JSON embedded state first, then HTML."""

    # Strategy 1: window.__PG_PROPS__ or __INITIAL_STATE__
    for pattern in [
        r'window\.__PG_PROPS__\s*=\s*({.+?});\s*</script>',
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*</script>',
        r'window\.__STATE__\s*=\s*({.+?});\s*</script>',
        r'id="__NEXT_DATA__"[^>]*>({.+?})</script>',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                result = parse_state_json(data, what, where)
                if result["listings"]:
                    Actor.log.info(f"Parsed via embedded JSON state ({pattern[:30]})")
                    return result
            except Exception as e:
                Actor.log.debug(f"State JSON parse error: {e}")

    # Strategy 2: JSON-LD structured data
    json_ld_blocks = re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    )
    ld_listings = []
    for block in json_ld_blocks:
        try:
            ld = json.loads(block.strip())
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if item.get("@type") in ("LocalBusiness", "Restaurant", "Store", "Organization"):
                    ld_listings.append(extract_from_jsonld(item, what, where))
        except Exception:
            pass
    if ld_listings:
        Actor.log.info(f"Parsed {len(ld_listings)} items via JSON-LD")
        total_m = re.search(r'"totalResults"\s*:\s*(\d+)', html)
        total = int(total_m.group(1)) if total_m else len(ld_listings)
        return {"listings": ld_listings, "total_count": total}

    # Strategy 3: HTML regex fallback
    return parse_html_fallback(html, what, where)


def parse_state_json(state: dict, what: str, where: str) -> dict:
    """Navigate state tree to find listings array."""

    def find_list(obj, depth=0):
        if depth > 8:
            return None
        if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict):
            if any(k in obj[0] for k in ("name", "ragioneSociale", "title", "denominazione")):
                return obj
        if isinstance(obj, dict):
            # Priority keys
            for key in ("listings", "results", "items", "list", "businesses", "aziende", "entries"):
                if key in obj:
                    found = find_list(obj[key], depth + 1)
                    if found:
                        return found
            for v in obj.values():
                found = find_list(v, depth + 1)
                if found:
                    return found
        return None

    def find_total(obj, depth=0):
        if depth > 8:
            return 0
        if isinstance(obj, dict):
            for key in ("total", "totalCount", "count", "totale", "totalResults", "numResults"):
                if key in obj and isinstance(obj[key], int):
                    return obj[key]
            for v in obj.values():
                t = find_total(v, depth + 1)
                if t:
                    return t
        return 0

    items = find_list(state) or []
    total = find_total(state)

    listings = []
    for item in items:
        listing = extract_listing_from_json(item, what, where)
        if listing and listing.get("name"):
            listings.append(listing)

    return {"listings": listings, "total_count": total}


def extract_from_jsonld(item: dict, what: str, where: str) -> dict:
    """Extract listing from JSON-LD LocalBusiness schema."""
    addr = item.get("address", {})
    geo = item.get("geo", {})
    return {
        "id": item.get("@id", item.get("url", "")),
        "name": clean_text(item.get("name", "")),
        "subtitle": "",
        "description": clean_text(item.get("description", "")),
        "category": clean_text(item.get("@type", what)),
        "phone": clean_phone(item.get("telephone", "")),
        "email": clean_text(item.get("email", "")),
        "website": clean_text(item.get("url", "")),
        "address": clean_text(addr.get("streetAddress", "") if isinstance(addr, dict) else str(addr)),
        "city": clean_text(addr.get("addressLocality", where) if isinstance(addr, dict) else where),
        "province": clean_text(addr.get("addressRegion", "") if isinstance(addr, dict) else ""),
        "postalCode": clean_text(addr.get("postalCode", "") if isinstance(addr, dict) else ""),
        "latitude": float(geo.get("latitude", 0)) or None,
        "longitude": float(geo.get("longitude", 0)) or None,
        "rating": float(item.get("aggregateRating", {}).get("ratingValue", 0)) or None,
        "reviewCount": item.get("aggregateRating", {}).get("reviewCount"),
        "image": item.get("image", ""),
        "facebook": "",
        "instagram": "",
        "searchWhat": what,
        "searchWhere": where,
        "sourceUrl": item.get("url", ""),
    }


def extract_listing_from_json(item: dict, what: str, where: str) -> dict:
    """Normalize a single JSON listing from state."""
    place = item.get("place", item.get("address", item.get("indirizzo", {})))
    if isinstance(place, str):
        address_str, city, province, postal_code = place, where, "", ""
        lat = lon = None
    else:
        address_str = clean_text(place.get("address", place.get("street", place.get("via", ""))))
        city = clean_text(place.get("locality", place.get("city", place.get("citta", where))))
        province = clean_text(place.get("region", place.get("province", place.get("provincia", ""))))
        postal_code = clean_text(place.get("postal-code", place.get("postalCode", place.get("cap", ""))))
        lat = place.get("latitude", place.get("lat"))
        lon = place.get("longitude", place.get("lon", place.get("lng")))

    raw_phone = item.get("telephone", item.get("phone", item.get("tel", item.get("telefono", ""))))
    phone = clean_phone(str(raw_phone)) if raw_phone else ""

    rating = item.get("rating", item.get("score", item.get("voto", item.get("stelle"))))
    try:
        rating = float(rating) if rating is not None else None
    except (ValueError, TypeError):
        rating = None

    social = item.get("social", {})
    if isinstance(social, list):
        social = {s.get("type", "x"): s.get("url", "") for s in social if isinstance(s, dict)}

    return {
        "id": str(item.get("id", item.get("pgId", item.get("codice", "")))),
        "name": clean_text(
            item.get("name", item.get("ragioneSociale", item.get("title", item.get("denominazione", ""))))
        ),
        "subtitle": clean_text(item.get("subtitle", item.get("sottotitolo", ""))),
        "description": clean_text(item.get("description", item.get("descrizione", ""))),
        "category": clean_text(item.get("category", item.get("categoria", what))),
        "phone": phone,
        "email": clean_text(item.get("email", item.get("mail", ""))),
        "website": clean_text(item.get("website", item.get("sito", item.get("url", "")))),
        "address": address_str,
        "city": city,
        "province": province,
        "postalCode": postal_code,
        "latitude": float(lat) if lat else None,
        "longitude": float(lon) if lon else None,
        "rating": rating,
        "reviewCount": item.get("reviewCount", item.get("reviews", item.get("numRecensioni"))),
        "image": item.get("image", item.get("foto", item.get("logo", item.get("immagine", "")))),
        "facebook": social.get("facebook", "") if isinstance(social, dict) else "",
        "instagram": social.get("instagram", "") if isinstance(social, dict) else "",
        "searchWhat": what,
        "searchWhere": where,
        "sourceUrl": item.get("sourceUrl", item.get("pgUrl", "")),
    }


def parse_html_fallback(html: str, what: str, where: str) -> dict:
    """Last resort regex HTML parser."""
    listings = []

    # Try to find business cards in various markup patterns
    card_patterns = [
        r'<article[^>]+>(.*?)</article>',
        r'<div[^>]+class="[^"]*(?:listing|result|business|card)[^"]*"[^>]*>(.*?)</div>\s*</div>',
        r'<li[^>]+class="[^"]*(?:listing|result)[^"]*"[^>]*>(.*?)</li>',
    ]

    blocks = []
    for pattern in card_patterns:
        blocks = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        if len(blocks) >= 2:
            break

    Actor.log.info(f"HTML fallback: found {len(blocks)} raw blocks")

    for block in blocks:
        # Extract fields via regex
        def extract(patterns_list):
            for p in patterns_list:
                m = re.search(p, block, re.DOTALL | re.IGNORECASE)
                if m:
                    return clean_text(re.sub(r"<[^>]+>", "", m.group(1)))
            return ""

        name = extract([
            r'class="[^"]*(?:name|titolo|denominazione)[^"]*"[^>]*>(.*?)</',
            r'<h[1-3][^>]*>(.*?)</h[1-3]>',
        ])
        if not name:
            continue

        phone = clean_phone(extract([
            r'class="[^"]*(?:phone|tel|telefono)[^"]*"[^>]*>(.*?)</',
            r'href="tel:([^"]+)"',
        ]))
        address = extract([r'class="[^"]*(?:address|indirizzo)[^"]*"[^>]*>(.*?)</'])
        category = extract([r'class="[^"]*(?:category|categoria)[^"]*"[^>]*>(.*?)</']) or what
        email_m = re.search(r'[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}', block)
        web_m = re.search(r'href="(https?://(?!(?:www\.)?paginegialle\.it)[^"]+)"', block)

        listings.append({
            "id": "", "name": name, "subtitle": "", "description": "",
            "category": category,
            "phone": phone,
            "email": email_m.group(0) if email_m else "",
            "website": web_m.group(1) if web_m else "",
            "address": address, "city": where,
            "province": "", "postalCode": "",
            "latitude": None, "longitude": None,
            "rating": None, "reviewCount": None,
            "image": "", "facebook": "", "instagram": "",
            "searchWhat": what, "searchWhere": where, "sourceUrl": "",
        })

    total_m = re.search(r'"(?:total|totalCount|numResults)"\s*:\s*(\d+)', html)
    total = int(total_m.group(1)) if total_m else len(listings)

    return {"listings": listings, "total_count": total}
