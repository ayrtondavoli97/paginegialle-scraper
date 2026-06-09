"""
PagineGialle.it Business Scraper
Apify Actor - ayrtondavoli97/paginegialle-scraper

Architecture (discovered by reverse engineering):
- The 661KB search page HTML contains ALL listings inline in the DOM
- jimpres.cgi / pgimpres.cgi are tracking pixels, NOT data endpoints
- Pagination is done via ?pg=2, ?pg=3 on the search page URL
- Each page is ~661KB with ~25 listings
"""

import asyncio
import re
import json

import httpx
from apify import Actor
from .utils import clean_phone, clean_text

SEARCH_BASE = "https://www.paginegialle.it/ricerca/{what}/{where}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.paginegialle.it/",
}


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        searches          = inp.get("searches", [])
        max_results       = inp.get("maxResults", 200)
        only_with_phone   = inp.get("onlyWithPhone", False)
        only_with_website = inp.get("onlyWithWebsite", False)
        only_with_email   = inp.get("onlyWithEmail", False)

        if not searches:
            Actor.log.error("Input 'searches' is empty.")
            return

        Actor.log.info("Direct connection (no proxy)")
        kv          = await Actor.open_key_value_store()
        dataset     = await Actor.open_dataset()
        total_saved = 0

        for search_item in searches:
            what  = search_item.get("what", "").strip()
            where = search_item.get("where", "").strip()
            if not what or not where:
                continue

            Actor.log.info(f"▶ '{what}' in '{where}'")
            results = await scrape_search(
                what=what, where=where,
                max_results=max_results,
                only_with_phone=only_with_phone,
                only_with_website=only_with_website,
                only_with_email=only_with_email,
                kv=kv,
            )

            if results:
                await dataset.push_data(results)
                total_saved += len(results)
                Actor.log.info(f"✔ {len(results)} saved for '{what}'/'{where}'")
            else:
                Actor.log.warning(f"✘ 0 results for '{what}'/'{where}'")

        Actor.log.info(f"Done. Total: {total_saved}")


async def scrape_search(what, where, max_results,
                        only_with_phone, only_with_website, only_with_email, kv):

    results    = []
    seen_ids   = set()
    what_slug  = normalize_slug(what)
    where_slug = normalize_slug(where)
    page       = 1
    total_count = 0

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True,
                                  timeout=httpx.Timeout(30.0)) as client:
        while len(results) < max_results:
            url = f"{SEARCH_BASE.format(what=what_slug, where=where_slug)}"
            if page > 1:
                url += f"?pg={page}"

            Actor.log.info(f"GET page {page}: {url}")
            try:
                resp = await client.get(url)
            except Exception as e:
                Actor.log.error(f"Request error: {e}")
                break

            Actor.log.info(f"HTTP {resp.status_code} — {len(resp.text)} chars")
            if resp.status_code != 200:
                break

            html = resp.text

            # On page 1: extract total count and save debug info
            if page == 1:
                total_count = extract_total_count(html)
                Actor.log.info(f"Total count: {total_count}")

                # Save a 5KB slice around the listing area for debug
                listing_pos = html.find('class="listing"')
                entry_pos   = html.find('class="entry ')
                await kv.set_value(f"debug_{what}_{where}", {
                    "html_len":       len(html),
                    "total_count":    total_count,
                    "listing_div_at": listing_pos,
                    "entry_div_at":   entry_pos,
                    "listing_snippet": html[listing_pos:listing_pos+2000] if listing_pos > 0 else "",
                    "entry_snippet":   html[entry_pos:entry_pos+2000] if entry_pos > 0 else "",
                    # Save chars around where listings should be (after filters)
                    "mid_html_120k":   html[118000:123000] if len(html) > 120000 else html[-5000:],
                    "mid_html_150k":   html[148000:153000] if len(html) > 150000 else "",
                    "mid_html_200k":   html[198000:203000] if len(html) > 200000 else "",
                })
                Actor.log.info("Debug info saved to KV")

                # Stop if no results at all
                if total_count == 0:
                    Actor.log.warning("Total count is 0, stopping")
                    break

            # Parse listings from this page's HTML
            listings = parse_listings(html, what, where)
            Actor.log.info(f"Page {page}: {len(listings)} listings parsed")

            if not listings:
                Actor.log.info("No listings found, stopping")
                break

            for item in listings:
                uid = item.get("id") or (item.get("name","") + item.get("address",""))
                if uid and uid in seen_ids: continue
                if uid: seen_ids.add(uid)
                if only_with_phone   and not item.get("phone"):   continue
                if only_with_website and not item.get("website"): continue
                if only_with_email   and not item.get("email"):   continue
                results.append(item)
                if len(results) >= max_results: break

            Actor.log.info(f"Running total: {len(results)}/{max_results}")
            if len(results) >= max_results:
                break

            # Check if there's a next page
            if not has_next_page(html, page):
                Actor.log.info("No more pages")
                break

            page += 1
            await asyncio.sleep(1.0)

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[\s_/]+", "-", text)
    for src, dst in [("àáâãäå","a"),("èéêë","e"),("ìíîï","i"),("òóôõö","o"),("ùúûü","u")]:
        for c in src: text = text.replace(c, dst)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return re.sub(r"-+", "-", text).strip("-")


def extract_total_count(html: str) -> int:
    """Extract total result count from page."""
    # From feOptions QTA param
    m = re.search(r'QTA=(\d+)', html)
    if m: return int(m.group(1))
    # From page text
    m = re.search(r'"totalCount"\s*:\s*(\d+)', html)
    if m: return int(m.group(1))
    m = re.search(r'(\d+)\s+risultati', html, re.IGNORECASE)
    if m: return int(m.group(1))
    return 0


def has_next_page(html: str, current_page: int) -> bool:
    """Check if there's a next page link."""
    next_pattern = rf'pg={current_page + 1}'
    return next_pattern in html or f'?pg={current_page+1}' in html


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_listings(html: str, what: str, where: str) -> list[dict]:
    """
    Parse business listings from PagineGialle search page HTML.
    The listings use class="entry" divs within class="listing" container.
    """
    listings = []

    # Strategy 1: JSON-LD structured data (most reliable)
    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    ):
        try:
            ld = json.loads(m.group(1).strip())
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                t = item.get("@type", "")
                if isinstance(t, list): t = t[0] if t else ""
                if any(x in str(t) for x in ("Business","Restaurant","Store","Organization","Service","Food")):
                    listings.append(extract_jsonld_item(item, what, where))
        except Exception:
            pass

    if listings:
        Actor.log.info(f"JSON-LD strategy: {len(listings)} items")
        return listings

    # Strategy 2: class="entry" divs (PagineGialle v7 listing cards)
    entry_blocks = re.findall(
        r'<(?:div|li|article)[^>]+class="[^"]*\bentry\b[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not entry_blocks:
        # Try wider pattern
        entry_blocks = re.findall(
            r'<(?:div|li|article)[^>]+class="[^"]*(?:entry|result-item|listing-item|company-card)[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
            html, re.DOTALL | re.IGNORECASE
        )

    Actor.log.info(f"entry blocks found: {len(entry_blocks)}")
    for block in entry_blocks:
        item = parse_entry_block(block, what, where)
        if item and item.get("name") and not is_section_header(item["name"]):
            listings.append(item)

    if listings:
        return listings

    # Strategy 3: microformat hCard
    vcard_blocks = re.findall(
        r'<(?:div|li|article)[^>]+class="[^"]*\bvcard\b[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
        html, re.DOTALL | re.IGNORECASE
    )
    for block in vcard_blocks:
        item = parse_entry_block(block, what, where)
        if item and item.get("name") and not is_section_header(item["name"]):
            listings.append(item)

    return listings


def is_section_header(name: str) -> bool:
    skip = ["più di", "risultati fuori", "ricerche correlate", "risultati per",
            "in zona", "annunci correlati", "altri risultati", "sponsored"]
    return any(k in name.lower() for k in skip)


def extract_jsonld_item(item: dict, what: str, where: str) -> dict:
    addr = item.get("address", {})
    geo  = item.get("geo", {})
    agg  = item.get("aggregateRating", {}) or {}
    if not isinstance(addr, dict): addr = {}
    if not isinstance(geo, dict):  geo  = {}
    return {
        "id":          item.get("@id", ""),
        "name":        clean_text(item.get("name", "")),
        "subtitle":    "",
        "description": clean_text(item.get("description", "")),
        "category":    clean_text(str(item.get("@type", what))),
        "phone":       clean_phone(item.get("telephone", "")),
        "email":       clean_text(item.get("email", "")),
        "website":     clean_text(item.get("url", "")),
        "address":     clean_text(addr.get("streetAddress", "")),
        "city":        clean_text(addr.get("addressLocality", where)),
        "province":    clean_text(addr.get("addressRegion", "")),
        "postalCode":  clean_text(addr.get("postalCode", "")),
        "latitude":    float(geo.get("latitude",  0)) or None,
        "longitude":   float(geo.get("longitude", 0)) or None,
        "rating":      float(agg.get("ratingValue", 0)) or None,
        "reviewCount": agg.get("reviewCount"),
        "image":       item.get("image", ""),
        "facebook":    "", "instagram":    "",
        "searchWhat":  what, "searchWhere": where,
        "sourceUrl":   item.get("url", ""),
    }


def parse_entry_block(block: str, what: str, where: str) -> dict | None:
    def get(patterns):
        for p in patterns:
            m = re.search(p, block, re.DOTALL | re.IGNORECASE)
            if m:
                return clean_text(re.sub(r"<[^>]+>", "", m.group(1)))
        return ""

    name = get([
        r'class="[^"]*\b(?:org|fn|name|denominazione|insegna|businessName|company-name|entry-title)[^"]*"[^>]*>(.*?)</',
        r'itemprop="name"[^>]*>(.*?)</',
        r'<h[123][^>]*class="[^"]*(?:name|title)[^"]*"[^>]*>(.*?)</h[123]>',
        r'<h[123][^>]*>(.*?)</h[123]>',
    ])
    if not name:
        return None

    phone = clean_phone(get([
        r'href="tel:([^"]+)"',
        r'class="[^"]*\b(?:tel|phone|telefono)[^"]*"[^>]*>(.*?)</',
        r'itemprop="telephone"[^>]*>(.*?)</',
    ]))
    address = get([
        r'class="[^"]*(?:street-address|adr|address|indirizzo)[^"]*"[^>]*>(.*?)</',
        r'itemprop="streetAddress"[^>]*>(.*?)</',
    ])
    city = get([
        r'class="[^"]*(?:locality|city|citta)[^"]*"[^>]*>(.*?)</',
        r'itemprop="addressLocality"[^>]*>(.*?)</',
    ]) or where
    province = get([
        r'class="[^"]*(?:region|province|provincia)[^"]*"[^>]*>(.*?)</',
        r'itemprop="addressRegion"[^>]*>(.*?)</',
    ])
    postcode = get([
        r'class="[^"]*(?:postal-code|cap)[^"]*"[^>]*>(.*?)</',
        r'itemprop="postalCode"[^>]*>(.*?)</',
    ])
    category = get([
        r'class="[^"]*(?:category|categoria|type)[^"]*"[^>]*>(.*?)</',
    ]) or what

    web_m = re.search(
        r'href="(https?://(?!(?:www\.)?paginegialle\.it)[^"]+)"[^>]*(?:class="[^"]*(?:url|website|sito)[^"]*")?',
        block)
    website = web_m.group(1) if web_m else ""

    em_m  = re.search(r'href="mailto:([^"]+)"', block)
    email = em_m.group(1) if em_m else ""

    id_m  = re.search(r'data-(?:cid|id|pgid)="([^"]+)"', block, re.IGNORECASE)
    bid   = id_m.group(1) if id_m else ""

    lat_m = re.search(r'data-lat="([^"]+)"', block)
    lon_m = re.search(r'data-(?:lon|lng)="([^"]+)"', block)
    lat   = float(lat_m.group(1)) if lat_m else None
    lon   = float(lon_m.group(1)) if lon_m else None

    rating_m = re.search(r'itemprop="ratingValue"[^>]*content="([^"]+)"', block)
    rating   = float(rating_m.group(1)) if rating_m else None

    src_m = re.search(r'href="(https?://(?:www\.)?paginegialle\.it/[^"]+)"', block)
    source = src_m.group(1) if src_m else ""

    img_m = re.search(r'<img[^>]+src="(https?://[^"]+(?:jpg|jpeg|png|webp)[^"]*)"', block, re.IGNORECASE)
    image = img_m.group(1) if img_m else ""

    return {
        "id": bid, "name": name, "subtitle": "",
        "description": get([r'class="[^"]*(?:note|description|descrizione)[^"]*"[^>]*>(.*?)</']),
        "category": category, "phone": phone, "email": email, "website": website,
        "address": address, "city": city, "province": province, "postalCode": postcode,
        "latitude": lat, "longitude": lon, "rating": rating, "reviewCount": None,
        "image": image, "facebook": "", "instagram": "",
        "searchWhat": what, "searchWhere": where, "sourceUrl": source,
    }
