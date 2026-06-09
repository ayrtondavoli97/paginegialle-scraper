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

        for s_idx, search_item in enumerate(searches):
            what  = search_item.get("what", "").strip()
            where = search_item.get("where", "").strip()
            if not what or not where:
                continue

            # Delay between searches to avoid rate limiting (HTTP 202)
            if s_idx > 0:
                # 20s cooldown between searches to avoid 202 rate limit
                # PagineGialle tracks by IP+session, fresh delay helps
                Actor.log.info("Cooling down 20s between searches...")
                await asyncio.sleep(20.0)

            Actor.log.info(f"▶ [{s_idx+1}/{len(searches)}] '{what}' in '{where}'")
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



async def fetch_district(client: httpx.AsyncClient, url: str,
                         what: str, where: str, semaphore: asyncio.Semaphore) -> list[dict]:
    """Fetch and parse a single district page. Uses semaphore for concurrency control."""
    async with semaphore:
        try:
            resp = await client.get(url)
            if resp.status_code == 202:
                # Rate limited: wait and retry once
                await asyncio.sleep(5.0)
                resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text
            return parse_listings(html, what, where)
        except Exception as e:
            Actor.log.debug(f"District fetch error ({url.split('/')[-1][:30]}): {e}")
            return []


async def scrape_districts(district_urls, what, where,
                           max_results, seen_ids,
                           only_with_phone, only_with_website, only_with_email):
    """
    Scrape district sub-pages concurrently in batches.
    Batch size 8 with 1.5s between batches = ~20s for 100 districts vs 200s sequential.
    """
    results = []
    BATCH_SIZE = 8
    BATCH_DELAY = 1.5  # seconds between batches
    consecutive_zeros = 0

    # Semaphore limits concurrent connections
    semaphore = asyncio.Semaphore(BATCH_SIZE)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True,
                                 timeout=httpx.Timeout(20.0),
                                 limits=httpx.Limits(max_connections=10)) as client:

        batches = [district_urls[i:i+BATCH_SIZE] for i in range(0, len(district_urls), BATCH_SIZE)]
        Actor.log.info(f"Districts: {len(district_urls)} URLs → {len(batches)} batches of {BATCH_SIZE}")

        for b_idx, batch in enumerate(batches):
            if len(results) >= max_results:
                break

            # Fetch all URLs in this batch concurrently
            tasks = [fetch_district(client, url, what, where, semaphore) for url in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            new_this_batch = 0
            for listings in batch_results:
                if isinstance(listings, Exception) or not listings:
                    continue
                for item in listings:
                    if not item or not item.get("name") or is_section_header(item["name"]):
                        continue
                    uid = item.get("id") or item.get("name","").lower().strip()
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)
                    if only_with_phone   and not item.get("phone"):   continue
                    if only_with_website and not item.get("website"): continue
                    if only_with_email   and not item.get("email"):   continue
                    results.append(item)
                    new_this_batch += 1
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

            Actor.log.info(
                f"Batch {b_idx+1}/{len(batches)}: +{new_this_batch} new | "
                f"total {len(results)}/{max_results}"
            )

            # Early stop: if 3 consecutive batches yield 0 new results, stop
            if new_this_batch == 0:
                consecutive_zeros = consecutive_zeros + 1 if b_idx > 0 else 1
            else:
                consecutive_zeros = 0

            if consecutive_zeros >= 3:
                Actor.log.info(f"3 consecutive zero-result batches — stopping early")
                break

            # Short delay between batches to stay under rate limit
            if b_idx < len(batches) - 1:
                await asyncio.sleep(BATCH_DELAY)

    return results


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
            if resp.status_code == 202:
                Actor.log.warning(f"HTTP 202 rate limit — sleeping 30s and retrying")
                await asyncio.sleep(30.0)
                try:
                    resp = await client.get(url)
                    Actor.log.info(f"Retry: HTTP {resp.status_code} — {len(resp.text)} chars")
                    if resp.status_code == 202:
                        Actor.log.warning("Still 202 — sleeping 60s more")
                        await asyncio.sleep(60.0)
                        resp = await client.get(url)
                        Actor.log.info(f"Retry2: HTTP {resp.status_code}")
                        if resp.status_code == 202:
                            Actor.log.warning("Persistent 202 — skipping this search")
                            break
                except Exception as e:
                    Actor.log.error(f"Retry failed: {e}")
                    break
            if resp.status_code != 200:
                break

            html = resp.text

            # On page 1: extract total count and save debug info
            if page == 1:
                page1_html = html  # Save for district extraction
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
                    "mid_html_200k":   html[198000:210000] if len(html) > 200000 else "",
                    "mid_html_210k":   html[208000:225000] if len(html) > 210000 else "",
                    "mid_html_250k":   html[248000:260000] if len(html) > 250000 else "",
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

            new_this_page = 0
            for item in listings:
                uid = item.get("id") or (item.get("name","").lower().strip() + "|" + item.get("sourceUrl",""))
                if not uid or uid == "|": uid = item.get("name","").lower().strip()
                if uid in seen_ids: continue
                seen_ids.add(uid)
                new_this_page += 1
                if only_with_phone   and not item.get("phone"):   continue
                if only_with_website and not item.get("website"): continue
                if only_with_email   and not item.get("email"):   continue
                results.append(item)
                if len(results) >= max_results: break

            Actor.log.info(f"Page {page}: {new_this_page} new, {len(listings)-new_this_page} dupes | total {len(results)}/{max_results}")
            if new_this_page == 0:
                if page == 2:
                    # PagineGialle repeats page 1 on page 2+ — switch to district mode
                    Actor.log.info("Page 2 all dupes → switching to district sub-searches")
                    district_urls = extract_districts(page1_html, what_slug, where_slug)
                    if district_urls:
                        district_results = await scrape_districts(
                            district_urls=district_urls,
                            what=what, where=where,
                            max_results=max_results - len(results),
                            seen_ids=seen_ids,
                            only_with_phone=only_with_phone,
                            only_with_website=only_with_website,
                            only_with_email=only_with_email,
                        )
                        results.extend(district_results)
                        Actor.log.info(f"Districts added {len(district_results)} results")
                Actor.log.info("Stopping main pagination")
                break
            if len(results) >= max_results:
                break

            # Check if there's a next page
            next_found = has_next_page(html, page)
            Actor.log.info(f"has_next_page(page={page}): {next_found}")
            if not next_found:
                # Last check: if we got full page of results and total says more, force continue
                if len(listings) >= 20 and total_count > len(results):
                    Actor.log.info(f"Force continue: {len(results)} < total {total_count}")
                else:
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


def extract_districts(html: str, what_slug: str, where_slug: str) -> list[str]:
    """
    Extract real geographic sub-area URLs from the PagineGialle district chip box.
    Filters out filter URLs (?f=...) and keeps only actual location variants.
    """
    pattern = rf'href="(https://www\.paginegialle\.it/ricerca/{re.escape(what_slug)}/[^"]+)"' 
    all_urls = list(dict.fromkeys(re.findall(pattern, html, re.IGNORECASE)))

    # Keep only URLs that are location-based (no ?f= query params, no fragments)
    # and represent a different sub-location (not the base city URL)
    base = f"https://www.paginegialle.it/ricerca/{what_slug}/{where_slug}"
    district_urls = []
    for url in all_urls:
        # Skip filter URLs (?f=), the base city URL, and any with query strings
        if "?" in url or "#" in url:
            continue
        if url.rstrip("/").lower() == base.rstrip("/").lower():
            continue
        district_urls.append(url)

    Actor.log.info(f"District URLs: {len(all_urls)} found, {len(district_urls)} location-based")
    return district_urls


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
    """Check if there's a next page link in PagineGialle pagination."""
    next_pg = current_page + 1
    # PagineGialle pagination patterns
    patterns = [
        f'pg={next_pg}',
        f'?pg={next_pg}',
        f'&pg={next_pg}',
        f'"pg":{next_pg}',
        'rel="next"',
        f'page={next_pg}',
    ]
    return any(p in html for p in patterns)


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_listings(html: str, what: str, where: str) -> list[dict]:
    """
    Parse business listings from PagineGialle search page HTML.
    PagineGialle v7 uses class="search-itm__rag" for the business name h2.
    Each card has class="search-itm__content" and class="search-itm__dx".
    Cards start ~200KB into the 661KB page.
    """
    listings = []

    # Strategy 1: JSON-LD (only present on detail pages, not listing pages)
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
        Actor.log.info(f"JSON-LD: {len(listings)} items")
        return listings

    # Strategy 2: PagineGialle v7 — anchor on outer card div
    # class="search-itm search-itm--new card-listing..."
    # This gives us the complete card including address and phone

    card_positions = [m.start() for m in re.finditer(
        r'class="search-itm[^"]*card-listing[^"]*"', html)]
    Actor.log.info(f"card-listing positions: {len(card_positions)} found")

    if not card_positions:
        # Fallback: anchor on name h2
        card_positions = [m.start() for m in re.finditer(
            r'class="[^"]*search-itm__rag[^"]*"', html)]
        Actor.log.info(f"search-itm__rag fallback: {len(card_positions)} found")

    # Extract each card as the slice between consecutive card anchors
    # Go back up to 200 chars to find the real opening tag (before class= attribute)
    for i, pos in enumerate(card_positions):
        # Find the actual tag start (<div, <li, <article) before the class= pos
        tag_start = pos
        for offset in range(1, 200):
            c = html[pos - offset]
            if c == '<':
                tag_start = pos - offset
                break
            if c == '>' and offset > 1:  # hit previous tag end, stop
                break
        end = card_positions[i + 1] if i + 1 < len(card_positions) else pos + 15000
        block = html[tag_start:end]
        item = parse_search_itm_block(block, what, where)
        if item and item.get("name") and not is_section_header(item["name"]):
            listings.append(item)

    if listings:
        return listings

    # Strategy 3: broader class search fallback
    for pat in [
        r'class="[^"]*search-itm[^"]*"',
        r'data-tr="listing-search-itm-rag"',
        r'class="[^"]*entry[^"]*"',
        r'class="[^"]*vcard[^"]*"',
    ]:
        positions = [m.start() for m in re.finditer(pat, html, re.IGNORECASE)]
        if positions:
            Actor.log.info(f"Fallback pattern '{pat}': {len(positions)} hits")
            for pos in positions[:50]:
                block = html[max(0, pos - 200):pos + 3000]
                item = parse_search_itm_block(block, what, where)
                if item and item.get("name") and not is_section_header(item["name"]):
                    listings.append(item)
            if listings:
                break

    return listings


def parse_search_itm_block(block: str, what: str, where: str) -> dict | None:
    """Parse a PagineGialle v7 search-itm card block."""

    def get(patterns):
        for p in patterns:
            m = re.search(p, block, re.DOTALL | re.IGNORECASE)
            if m:
                raw = m.group(1)
                # Remove inner spans/icons, keep text
                raw = re.sub(r'<span class="icon[^"]*"[^>]*>.*?</span>', '', raw, flags=re.DOTALL)
                return clean_text(re.sub(r"<[^>]+>", "", raw))
        return ""

    # Name from search-itm__rag h2
    name = get([
        r'class="[^"]*search-itm__rag[^"]*"[^>]*>\s*(.*?)\s*</h[123]>',
        r'data-tr="listing-search-itm-rag"[^>]*>\s*(.*?)\s*</h[123]>',
        r'<h2[^>]*class="[^"]*search-itm[^"]*"[^>]*>(.*?)</h2>',
    ])
    if not name:
        return None

    # data-user UUID from card opening tag
    user_m = re.search(r'data-user="([0-9a-fA-F\-]{30,})"|data-user="([^"]+)"', block[:600])
    data_user = (user_m.group(1) or user_m.group(2)) if user_m else ""

    # Source URL - paginegialle.it profile link
    # e.g. https://www.paginegialle.it/emozioninapoli or /ristorante-napoli
    SKIP_PATHS = ("/mappa/","/profilo/","/ricerca/","/static/","/servizi/",
                  "/shop/","/news/","/scheda/","/autocomplete/","/services/")
    source_url = ""
    for m in re.finditer(
        r'href="(https?://(?:www\.)?paginegialle\.it/([a-z0-9][^"?#\s]{1,80}))"',
        block
    ):
        url_candidate = m.group(1)
        path = m.group(2)
        if not any(path.startswith(s.lstrip("/")) or s in url_candidate for s in SKIP_PATHS):
            source_url = url_candidate
            break

    # Phone: class="search-itm__phone-item" inside hidden shownum div
    # Collect ALL phone numbers from this card
    phone_items = re.findall(
        r'class="[^"]*search-itm__phone-item[^"]*">\s*([0-9][\d\s]{6,14})<',
        block
    )
    phone = clean_phone(phone_items[0]) if phone_items else clean_phone(get([
        r'href="tel:([^"]+)"',
    ]))

    # Address: class="search-itm__adr" contains full address text
    adr_m = re.search(
        r'class="[^"]*search-itm__adr[^"]*"[^>]*>.*?<div[^>]*>\s*(.*?)\s*</div>',
        block, re.DOTALL | re.IGNORECASE
    )
    if adr_m:
        address = clean_text(re.sub(r'<[^>]+>', '', adr_m.group(1)))
    else:
        address = get([
            r'class="[^"]*(?:adr|address|indirizzo)[^"]*"[^>]*>(.*?)</',
            r'itemprop="streetAddress"[^>]*>(.*?)</',
        ])

    # Category: skip badges like "Suggerito"/"Consigliato", use search what
    # The real category label is in search-itm__label but often shows badge text
    raw_cat = get([
        r'data-tr="listing-search-itm-lbl"[^>]*>.*?<span>([^<]{4,})</span>',
        r'class="[^"]*(?:category|categoria|type|tipo)[^"]*"[^>]*>(.*?)</',
    ])
    # Filter out badge/status labels
    badge_words = {"suggerito", "consigliato", "sponsor", "in evidenza", "verificato", "aperto", "chiuso"}
    category = what if not raw_cat or raw_cat.lower() in badge_words else raw_cat

    # Rating - find the first rating div AFTER the name (pos ~500 in block)
    block_after_name = block[400:]  # skip image area before name
    rating_m = re.search(r'itemprop="ratingValue"[^>]*content="([^"]+)"', block_after_name)
    if not rating_m:
        # rating-stars--75 = 75/20 = 3.75 stars
        rating_m = re.search(r'class="rating-stars rating-stars--([0-9]+)"', block_after_name)
        if rating_m:
            val = int(rating_m.group(1))
            rating = round(val / 20, 1) if val > 5 else None
        else:
            rating = None
    else:
        try: rating = float(rating_m.group(1))
        except: rating = None

    # Image
    img_m = re.search(r'src="(https?://wips\.plug\.it[^"]+)"', block)
    if not img_m:
        img_m = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', block, re.IGNORECASE)
    image = img_m.group(1) if img_m else ""

    # ID: prefer data-user UUID, fallback to URL slug
    bid = data_user if data_user else ""
    if not bid and source_url:
        slug_m = re.search(r'/([a-z0-9\-]+)$', source_url)
        bid = slug_m.group(1) if slug_m else ""

    return {
        "id": bid, "name": name, "subtitle": "", "description": "",
        "category": category, "phone": phone, "email": "",
        "website": "", "address": address, "city": where,
        "province": "", "postalCode": "",
        "latitude": None, "longitude": None,
        "rating": rating, "reviewCount": None,
        "image": image, "facebook": "", "instagram": "",
        "searchWhat": what, "searchWhere": where,
        "sourceUrl": source_url,
    }


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
