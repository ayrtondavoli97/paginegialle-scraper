"""
PagineGialle.it Business Scraper - v2
Architecture:
  Step 1: GET paginegialle.it/ricerca/{what}/{where}
          → extract feOptions.shiny_pgimp_src (internal API URL)
  Step 2: GET ssc.paginegialle.it/cgi-bin/jimpres.cgi?...
          → parse HTML with listing cards (vcard microformat)
  Step 3: Paginate by incrementing PAGINA and INIZIO params
"""

import asyncio
import math
import re
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import httpx
from apify import Actor
from .utils import clean_phone, clean_text

SEARCH_BASE    = "https://www.paginegialle.it/ricerca/{what}/{where}"
RESULTS_PER_PAGE = 25  # NADV=25 in API


HEADERS_HTML = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.paginegialle.it/",
}

HEADERS_API = {
    **HEADERS_HTML,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Referer": "https://www.paginegialle.it/",
}


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        searches          = inp.get("searches", [])
        max_results       = inp.get("maxResults", 200)
        use_proxy         = inp.get("useApifyProxy", True)
        proxy_country     = inp.get("proxyCountry", "IT")
        only_with_phone   = inp.get("onlyWithPhone", False)
        only_with_website = inp.get("onlyWithWebsite", False)
        only_with_email   = inp.get("onlyWithEmail", False)

        if not searches:
            Actor.log.error("Input 'searches' is empty.")
            return

        # Apify internal proxy (10.x.x.x:8011) incompatible with httpx in LIMITED_PERMISSIONS.
        # Both paginegialle.it and ssc.paginegialle.it work fine direct.
        proxy_url = None
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
                proxy_url=proxy_url,
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


async def fetch(client: httpx.AsyncClient, url: str, headers: dict, kv=None, kv_key: str = "") -> str | None:
    """Fetch URL, return text or None. Saves raw to KV if key given."""
    try:
        resp = await client.get(url, headers=headers)
        Actor.log.info(f"HTTP {resp.status_code} — {len(resp.text)} chars — {str(resp.url)[:80]}")
        if kv and kv_key:
            await kv.set_value(kv_key, resp.text[:120_000],
                               content_type="text/html; charset=utf-8")
        if resp.status_code == 200:
            return resp.text
        Actor.log.warning(f"Non-200: {resp.status_code}")
        return None
    except Exception as e:
        Actor.log.error(f"Request error: {e}")
        if kv and kv_key:
            await kv.set_value(kv_key + "_err", {"error": str(e), "url": url})
        return None


def make_client(proxy_url: str | None) -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
    return httpx.AsyncClient(follow_redirects=True,
                             timeout=httpx.Timeout(30.0),
                             transport=transport)


async def scrape_search(what, where, max_results, proxy_url,
                        only_with_phone, only_with_website, only_with_email, kv):

    results    = []
    seen_ids   = set()
    what_slug  = normalize_slug(what)
    where_slug = normalize_slug(where)
    search_url = SEARCH_BASE.format(what=what_slug, where=where_slug)

    # ── Single shared client — cookies from step1 carry into step2/3 ──────
    async with make_client(None) as client:

        # Step 1: load search page → get feOptions with API URL + cookies
        Actor.log.info(f"Step 1: {search_url}")
        html = await fetch(client, search_url, HEADERS_HTML,
                           kv=kv, kv_key=f"search_{what}_{where}")
        if not html:
            Actor.log.error("Search page failed")
            return []

        # Log cookies received from step1
        cookies = dict(client.cookies)
        Actor.log.info(f"Session cookies after step1: {list(cookies.keys())}")

        # Step 2: extract internal API URL
        api_url = extract_api_url(html)
        if not api_url:
            Actor.log.error("shiny_pgimp_src not found in HTML")
            await kv.set_value(f"debug_{what}_{where}", {
                "msg": "shiny_pgimp_src not found",
                "html_head": html[:2000],
            })
            return []

        total_count = int(get_param(api_url, "QTA") or "0")
        results_per = int(get_param(api_url, "NADV") or "25")
        total_pages = min(
            math.ceil(total_count / results_per),
            math.ceil(max_results / results_per),
        ) if total_count > 0 else 10

        Actor.log.info(f"Step 2: API found — QTA={total_count} NADV={results_per} → {total_pages} pages")

        # Small delay so the server sees a realistic browsing pattern
        await asyncio.sleep(0.5)

        # Step 3: paginate API with same session
        for page in range(1, total_pages + 1):
            paged_url = set_pagination(api_url, page, results_per)
            Actor.log.info(f"API page {page}/{total_pages}: {paged_url[:120]}...")

            api_html = await fetch(client, paged_url, HEADERS_API,
                                   kv=kv, kv_key=f"api_{what}_{where}_p{page}" if page <= 2 else "")
            if not api_html:
                Actor.log.warning(f"Page {page} empty/failed, stopping")
                break

            if page == 1:
                await kv.set_value(f"parse_{what}_{where}", {
                    "api_html_len":  len(api_html),
                    "api_html_head": api_html[:1500],
                    "total_count":   total_count,
                })

            listings = parse_api_html(api_html, what, where)
            Actor.log.info(f"Page {page}: {len(listings)} listings parsed")

            if not listings:
                Actor.log.info("No listings on page, stopping")
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

            Actor.log.info(f"Running total: {len(results)}")
            if len(results) >= max_results:
                break
            await asyncio.sleep(0.8)

    return results


# ── URL helpers ───────────────────────────────────────────────────────────────

def normalize_slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[\s_/]+", "-", text)
    for src, dst in [("àáâãäå","a"),("èéêë","e"),("ìíîï","i"),("òóôõö","o"),("ùúûü","u")]:
        for c in src: text = text.replace(c, dst)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return re.sub(r"-+", "-", text).strip("-")


def extract_api_url(html: str) -> str | None:
    """Extract feOptions.shiny_pgimp_src from page HTML."""
    m = re.search(r'shiny_pgimp_src:\s*"(https://ssc\.paginegialle\.it[^"]+)"', html)
    if m:
        return m.group(1)
    # fallback: look for the URL in any context
    m = re.search(r'"(https://ssc\.paginegialle\.it/cgi-bin/jimpres\.cgi[^"]+)"', html)
    return m.group(1) if m else None


def get_param(url: str, param: str) -> str | None:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    vals   = params.get(param)
    return vals[0] if vals else None


def set_pagination(url: str, page: int, per_page: int) -> str:
    """Update PAGINA and INIZIO params for pagination."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["PAGINA"] = [str(page)]
    params["INIZIO"] = [str((page - 1) * per_page + 1)]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


# ── Parser for ssc.paginegialle.it API response ───────────────────────────────

def parse_api_html(html: str, what: str, where: str) -> list[dict]:
    """
    Parse the HTML returned by ssc.paginegialle.it/cgi-bin/jimpres.cgi
    This uses hCard/vCard microformat.
    """
    listings = []

    # Try JSON first (some API responses return JSON)
    try:
        data = json.loads(html)
        if isinstance(data, list):
            return [l for l in (extract_json_item(i, what, where) for i in data) if l]
        if isinstance(data, dict):
            items = data.get("results", data.get("items", data.get("data", [])))
            if items:
                return [l for l in (extract_json_item(i, what, where) for i in items) if l]
    except Exception:
        pass

    # Parse vCard HTML blocks
    # PagineGialle uses <div class="vcard"> or <li class="vcard">
    blocks = re.findall(
        r'<(?:div|li|article)[^>]+class="[^"]*vcard[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
        html, re.DOTALL | re.IGNORECASE
    )

    if not blocks:
        # Try broader patterns
        blocks = re.findall(
            r'<(?:div|li|article)[^>]+class="[^"]*(?:result|listing|item|company)[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
            html, re.DOTALL | re.IGNORECASE
        )

    Actor.log.info(f"API HTML: {len(html)} chars, {len(blocks)} vcard blocks found")

    for block in blocks:
        item = parse_vcard_block(block, what, where)
        if item and item.get("name"):
            listings.append(item)

    return listings


def parse_vcard_block(block: str, what: str, where: str) -> dict | None:
    """Parse a single vCard microformat block from PagineGialle API."""

    def get(patterns):
        for p in patterns:
            m = re.search(p, block, re.DOTALL | re.IGNORECASE)
            if m:
                return clean_text(re.sub(r"<[^>]+>", "", m.group(1)))
        return ""

    # Name: class="org" or class="fn" in hCard
    name = get([
        r'class="[^"]*\borg\b[^"]*"[^>]*>(.*?)</',
        r'class="[^"]*\bfn\b[^"]*"[^>]*>(.*?)</',
        r'class="[^"]*name[^"]*"[^>]*>(.*?)</',
        r'itemprop="name"[^>]*>(.*?)</',
    ])
    if not name:
        return None

    # Phone: class="tel" or href="tel:"
    phone = clean_phone(get([
        r'href="tel:([^"]+)"',
        r'class="[^"]*\btel\b[^"]*"[^>]*>(.*?)</',
        r'class="[^"]*phone[^"]*"[^>]*>(.*?)</',
        r'itemprop="telephone"[^>]*>(.*?)</',
    ]))

    # Address parts
    address  = get([r'class="[^"]*street-address[^"]*"[^>]*>(.*?)</', r'itemprop="streetAddress"[^>]*>(.*?)</',  r'class="[^"]*adr[^"]*"[^>]*>(.*?)</'])
    city     = get([r'class="[^"]*locality[^"]*"[^>]*>(.*?)</',       r'itemprop="addressLocality"[^>]*>(.*?)</']) or where
    province = get([r'class="[^"]*region[^"]*"[^>]*>(.*?)</',         r'itemprop="addressRegion"[^>]*>(.*?)</'])
    postcode = get([r'class="[^"]*postal-code[^"]*"[^>]*>(.*?)</',    r'itemprop="postalCode"[^>]*>(.*?)</'])

    # Website
    web_m = re.search(r'href="(https?://(?!(?:www\.)?paginegialle\.it)[^"]+)"[^>]*class="[^"]*url[^"]*"', block)
    if not web_m:
        web_m = re.search(r'class="[^"]*url[^"]*"[^>]*href="(https?://(?!(?:www\.)?paginegialle\.it)[^"]+)"', block)
    website = web_m.group(1) if web_m else ""

    # Email
    em_m  = re.search(r'href="mailto:([^"]+)"', block)
    email = em_m.group(1) if em_m else ""
    if not email:
        em_m = re.search(r'[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}', block)
        email = em_m.group(0) if em_m else ""

    # Category
    category = get([r'class="[^"]*category[^"]*"[^>]*>(.*?)</', r'class="[^"]*categoria[^"]*"[^>]*>(.*?)</']) or what

    # Rating
    rating_m = re.search(r'(?:rating|voto|stelle)[^>]*>([0-9.]+)<', block, re.IGNORECASE)
    rating   = float(rating_m.group(1)) if rating_m else None

    # ID: data-cid, data-id, or any UUID-like in block
    id_m = re.search(r'data-(?:cid|id|pgid)="([^"]+)"', block, re.IGNORECASE)
    if not id_m:
        id_m = re.search(r'([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})', block, re.IGNORECASE)
    bid = id_m.group(1) if id_m else ""

    # GPS
    lat_m = re.search(r'data-lat="([^"]+)"|itemprop="latitude"[^>]*content="([^"]+)"', block)
    lon_m = re.search(r'data-lon="([^"]+)"|itemprop="longitude"[^>]*content="([^"]+)"', block)
    lat   = float(lat_m.group(1) or lat_m.group(2)) if lat_m else None
    lon   = float(lon_m.group(1) or lon_m.group(2)) if lon_m else None

    # Image
    img_m = re.search(r'<img[^>]+src="([^"]+(?:jpg|jpeg|png|webp)[^"]*)"', block, re.IGNORECASE)
    image = img_m.group(1) if img_m else ""

    # Source URL
    src_m = re.search(r'href="(https?://(?:www\.)?paginegialle\.it/[^"]+)"', block)
    source_url = src_m.group(1) if src_m else ""

    return {
        "id":          bid,
        "name":        name,
        "subtitle":    "",
        "description": get([r'class="[^"]*(?:note|descrizione|description)[^"]*"[^>]*>(.*?)</']),
        "category":    category,
        "phone":       phone,
        "email":       email,
        "website":     website,
        "address":     address,
        "city":        city,
        "province":    province,
        "postalCode":  postcode,
        "latitude":    lat,
        "longitude":   lon,
        "rating":      rating,
        "reviewCount": None,
        "image":       image,
        "facebook":    "",
        "instagram":   "",
        "searchWhat":  what,
        "searchWhere": where,
        "sourceUrl":   source_url,
    }


def extract_json_item(item: dict, what: str, where: str) -> dict | None:
    if not isinstance(item, dict): return None
    place = item.get("place", item.get("address", {}))
    if not isinstance(place, dict): place = {}
    lat = place.get("latitude", place.get("lat"))
    lon = place.get("longitude", place.get("lon", place.get("lng")))
    raw_phone = item.get("telephone", item.get("phone", item.get("tel", "")))
    phone = clean_phone(str(raw_phone)) if raw_phone else ""
    try: rating = float(item.get("rating","")) if item.get("rating") else None
    except: rating = None
    return {
        "id":          str(item.get("id", item.get("pgId",""))),
        "name":        clean_text(item.get("name", item.get("ragioneSociale", item.get("denominazione","")))),
        "subtitle":    clean_text(item.get("subtitle","")),
        "description": clean_text(item.get("description", item.get("descrizione",""))),
        "category":    clean_text(item.get("category", item.get("categoria", what))),
        "phone":       phone,
        "email":       clean_text(item.get("email","")),
        "website":     clean_text(item.get("website", item.get("sito",""))),
        "address":     clean_text(place.get("address", place.get("street",""))),
        "city":        clean_text(place.get("locality", place.get("city", where))),
        "province":    clean_text(place.get("region","")),
        "postalCode":  clean_text(place.get("postalCode", place.get("cap",""))),
        "latitude":    float(lat) if lat else None,
        "longitude":   float(lon) if lon else None,
        "rating":      rating,
        "reviewCount": item.get("reviewCount"),
        "image":       item.get("image",""),
        "facebook":    "",
        "instagram":   "",
        "searchWhat":  what,
        "searchWhere": where,
        "sourceUrl":   item.get("url",""),
    }
