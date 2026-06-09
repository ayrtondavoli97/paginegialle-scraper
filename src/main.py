"""
PagineGialle.it Business Scraper
Apify Actor - ayrtondavoli97/paginegialle-scraper
"""

import asyncio
import math
import re
import json
import base64
from urllib.parse import urlparse

import httpx
from apify import Actor
from .utils import clean_phone, clean_text

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
    "Connection": "keep-alive",
    "Referer": "https://www.paginegialle.it/",
}


def make_client(proxy_url: str | None = None) -> httpx.AsyncClient:
    """
    Build httpx client. Apify proxy (10.x.x.x:8011) needs
    Proxy-Authorization header injected manually — httpx mounts
    it correctly when proxy= is a full http://user:pass@host:port string.
    """
    transport = None

    if proxy_url:
        parsed = urlparse(proxy_url)
        # Build proxy with explicit auth
        proxy_str = proxy_url  # httpx accepts user:pass@host:port directly
        transport = httpx.AsyncHTTPTransport(proxy=proxy_str)

    return httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
        transport=transport,
    )


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

        # ── Proxy setup ────────────────────────────────────────────────────
        proxy_url = None
        if use_proxy:
            proxy_cfg = await Actor.create_proxy_configuration(country_code=proxy_country)
            proxy_url = await proxy_cfg.new_url()
            p = urlparse(proxy_url)
            Actor.log.info(f"Proxy: {p.scheme}://***:***@{p.hostname}:{p.port}")

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
                Actor.log.info(f"✔ {len(results)} saved")
            else:
                Actor.log.warning(f"✘ 0 results for '{what}'/'{where}'")

        Actor.log.info(f"Done. Total: {total_saved}")


async def fetch_with_fallback(url: str, proxy_url: str | None, kv, label: str) -> httpx.Response | None:
    """
    Try fetching URL:
    1. With proxy (if provided)
    2. Without proxy (direct) if proxy fails
    Always saves raw HTML + status to KV for debug.
    """
    attempts = []
    if proxy_url:
        attempts.append(("proxy", proxy_url))
    attempts.append(("direct", None))  # always try direct as fallback

    for mode, purl in attempts:
        Actor.log.info(f"Attempt [{mode}]: GET {url}")
        try:
            async with make_client(purl) as client:
                resp = await client.get(url)
            Actor.log.info(f"[{mode}] HTTP {resp.status_code} — {len(resp.text)} chars")

            # Save raw to KV
            await kv.set_value(
                f"raw_{label}_{mode}",
                resp.text[:60_000],
                content_type="text/html; charset=utf-8",
            )

            if resp.status_code == 200:
                return resp
            elif resp.status_code == 407:
                Actor.log.warning(f"[{mode}] 407 proxy auth failed, trying next")
                continue
            elif resp.status_code == 429:
                Actor.log.warning(f"[{mode}] 429 rate limit, sleeping 10s")
                await asyncio.sleep(10)
                return resp
            else:
                Actor.log.warning(f"[{mode}] HTTP {resp.status_code}")
                return resp

        except Exception as e:
            Actor.log.error(f"[{mode}] Exception: {e}")
            await kv.set_value(f"error_{label}_{mode}", {"error": str(e), "url": url})
            continue

    Actor.log.error(f"All attempts failed for {url}")
    return None


async def scrape_search(what, where, max_results, proxy_url,
                        only_with_phone, only_with_website, only_with_email, kv):
    results     = []
    page        = 1
    total_pages = 1
    seen_ids    = set()
    ws          = normalize_slug(what)
    wr          = normalize_slug(where)

    while page <= total_pages and len(results) < max_results:
        url   = build_url(ws, wr, page)
        label = f"{what}_{where}_p{page}"

        resp = await fetch_with_fallback(url, proxy_url, kv, label)
        if resp is None or resp.status_code != 200:
            break

        data = parse_page(resp.text, what, where)

        if page == 1:
            await kv.set_value(f"parse_{what}_{where}", {
                "strategy":    data.get("strategy"),
                "listings":    len(data.get("listings", [])),
                "total_count": data.get("total_count"),
                "html_head":   resp.text[:1000],
            })
            Actor.log.info(
                f"Parse: strategy={data.get('strategy')} "
                f"listings={len(data.get('listings',[]))} "
                f"total={data.get('total_count')}"
            )
            tc = data.get("total_count", 0)
            if tc > 0:
                total_pages = min(
                    math.ceil(tc / RESULTS_PER_PAGE),
                    math.ceil(max_results / RESULTS_PER_PAGE),
                )
                Actor.log.info(f"~{tc} total → {total_pages} pages")
            else:
                total_pages = math.ceil(max_results / RESULTS_PER_PAGE)

        listings = data.get("listings", [])
        if not listings:
            Actor.log.info(f"Page {page}: no listings, stopping")
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

        Actor.log.info(f"Page {page}/{total_pages} → {len(results)} total")
        page += 1
        await asyncio.sleep(1.0)

    return results


# ── URL helpers ───────────────────────────────────────────────────────────────

def normalize_slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[\s_/]+", "-", text)
    for src, dst in [("àáâãäå","a"),("èéêë","e"),("ìíîï","i"),("òóôõö","o"),("ùúûü","u")]:
        for c in src: text = text.replace(c, dst)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return re.sub(r"-+", "-", text).strip("-")

def build_url(what: str, where: str, page: int) -> str:
    base = f"{BASE_URL}/ricerca/{what}/{where}"
    return f"{base}?pg={page}" if page > 1 else base


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_page(html: str, what: str, where: str) -> dict:
    # 1. Embedded JS state
    for pat in [
        r'window\.__PG_PROPS__\s*=\s*({.+?});\s*(?:</script>|window\.)',
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*(?:</script>|window\.)',
        r'window\.__STATE__\s*=\s*({.+?});\s*(?:</script>|window\.)',
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>({.+?})</script>',
        r'window\.pg\s*=\s*({.+?});\s*</script>',
    ]:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                result = parse_state_json(json.loads(m.group(1)), what, where)
                if result["listings"]:
                    result["strategy"] = "js-state"
                    return result
            except Exception:
                pass

    # 2. JSON-LD
    ld = parse_jsonld(html, what, where)
    if ld["listings"]:
        ld["strategy"] = "json-ld"
        return ld

    # 3. Inline JSON arrays
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        arr = re.search(r'(\[\s*\{.+?"(?:name|ragioneSociale|insegna)".+?\}\s*\])', m.group(1), re.DOTALL)
        if arr:
            try:
                items    = json.loads(arr.group(1))
                listings = [l for l in (extract_listing_from_json(i,what,where) for i in items) if l and l.get("name")]
                if listings:
                    return {"listings": listings, "total_count": len(listings), "strategy": "inline-json"}
            except Exception:
                pass

    result = parse_html_fallback(html, what, where)
    result["strategy"] = "html-regex"
    return result


def parse_state_json(state: dict, what: str, where: str) -> dict:
    def find_list(obj, depth=0):
        if depth > 10: return None
        if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict):
            if any(k in obj[0] for k in ("name","ragioneSociale","title","denominazione","insegna","businessName")):
                return obj
        if isinstance(obj, dict):
            for key in ("listings","results","items","list","businesses","aziende","entries","data","records"):
                if key in obj:
                    r = find_list(obj[key], depth+1)
                    if r: return r
            for v in obj.values():
                if isinstance(v, (dict,list)):
                    r = find_list(v, depth+1)
                    if r: return r
        return None

    def find_total(obj, depth=0):
        if depth > 8: return 0
        if isinstance(obj, dict):
            for k in ("total","totalCount","count","totale","totalResults","numResults","found"):
                if k in obj and isinstance(obj[k], int) and obj[k] > 0: return obj[k]
            for v in obj.values():
                if isinstance(v, (dict,list)):
                    t = find_total(v, depth+1)
                    if t: return t
        return 0

    items    = find_list(state) or []
    total    = find_total(state)
    listings = [l for l in (extract_listing_from_json(i,what,where) for i in items) if l and l.get("name")]
    return {"listings": listings, "total_count": total}


def parse_jsonld(html: str, what: str, where: str) -> dict:
    listings = []
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL|re.IGNORECASE):
        try:
            ld = json.loads(m.group(1).strip())
            for item in (ld if isinstance(ld,list) else [ld]):
                t = item.get("@type","")
                if isinstance(t,list): t = t[0] if t else ""
                if not any(x in t for x in ("Business","Restaurant","Store","Organization","Service","Company")): continue
                addr = item.get("address",{}); geo = item.get("geo",{}); agg = item.get("aggregateRating",{}) or {}
                listings.append({
                    "id": item.get("@id",""), "name": clean_text(item.get("name","")),
                    "subtitle":"", "description": clean_text(item.get("description","")),
                    "category": clean_text(str(t)),
                    "phone": clean_phone(item.get("telephone","")),
                    "email": clean_text(item.get("email","")),
                    "website": clean_text(item.get("url","")),
                    "address": clean_text(addr.get("streetAddress","") if isinstance(addr,dict) else str(addr)),
                    "city": clean_text(addr.get("addressLocality",where) if isinstance(addr,dict) else where),
                    "province": clean_text(addr.get("addressRegion","") if isinstance(addr,dict) else ""),
                    "postalCode": clean_text(addr.get("postalCode","") if isinstance(addr,dict) else ""),
                    "latitude": float(geo.get("latitude",0)) or None,
                    "longitude": float(geo.get("longitude",0)) or None,
                    "rating": float(agg.get("ratingValue",0)) or None,
                    "reviewCount": agg.get("reviewCount"),
                    "image": item.get("image",""), "facebook":"", "instagram":"",
                    "searchWhat": what, "searchWhere": where, "sourceUrl": item.get("url",""),
                })
        except Exception:
            pass
    total_m = re.search(r'"(?:total|totalResults|count)"\s*:\s*(\d+)', html)
    return {"listings": listings, "total_count": int(total_m.group(1)) if total_m else len(listings)}


def extract_listing_from_json(item: dict, what: str, where: str) -> dict | None:
    if not isinstance(item, dict): return None
    place = item.get("place", item.get("address", item.get("indirizzo", {})))
    if isinstance(place, str):
        address_str, city, province, postal_code, lat, lon = place, where, "", "", None, None
    else:
        if not isinstance(place, dict): place = {}
        address_str = clean_text(place.get("address", place.get("street", place.get("via",""))))
        city        = clean_text(place.get("locality", place.get("city", place.get("citta",where))))
        province    = clean_text(place.get("region",  place.get("province", place.get("provincia",""))))
        postal_code = clean_text(place.get("postal-code", place.get("postalCode", place.get("cap",""))))
        lat = place.get("latitude", place.get("lat"))
        lon = place.get("longitude", place.get("lon", place.get("lng")))

    raw_phone = item.get("telephone", item.get("phone", item.get("tel", item.get("telefono",""))))
    phone = clean_phone(str(raw_phone)) if raw_phone else ""
    rating = item.get("rating", item.get("score", item.get("voto")))
    try: rating = float(rating) if rating is not None else None
    except: rating = None
    social = item.get("social",{})
    if isinstance(social,list): social = {s.get("type","x"): s.get("url","") for s in social if isinstance(s,dict)}
    if not isinstance(social,dict): social = {}

    return {
        "id": str(item.get("id", item.get("pgId", item.get("codice","")))),
        "name": clean_text(item.get("name", item.get("ragioneSociale", item.get("title", item.get("denominazione", item.get("insegna","")))))),
        "subtitle": clean_text(item.get("subtitle", item.get("sottotitolo",""))),
        "description": clean_text(item.get("description", item.get("descrizione",""))),
        "category": clean_text(item.get("category", item.get("categoria", what))),
        "phone": phone, "email": clean_text(item.get("email", item.get("mail",""))),
        "website": clean_text(item.get("website", item.get("sito", item.get("url","")))),
        "address": address_str, "city": city, "province": province, "postalCode": postal_code,
        "latitude": float(lat) if lat else None, "longitude": float(lon) if lon else None,
        "rating": rating, "reviewCount": item.get("reviewCount", item.get("reviews", item.get("numRecensioni"))),
        "image": item.get("image", item.get("foto", item.get("logo",""))),
        "facebook": social.get("facebook",""), "instagram": social.get("instagram",""),
        "searchWhat": what, "searchWhere": where, "sourceUrl": item.get("sourceUrl", item.get("pgUrl","")),
    }


def parse_html_fallback(html: str, what: str, where: str) -> dict:
    listings, blocks = [], []
    for pattern in [
        r'<article[^>]+>(.*?)</article>',
        r'<div[^>]+class="[^"]*(?:listing|result|business|card)[^"]*"[^>]*>(.*?(?:</div>\s*){2})',
        r'<li[^>]+class="[^"]*(?:listing|result)[^"]*"[^>]*>(.*?)</li>',
    ]:
        blocks = re.findall(pattern, html, re.DOTALL|re.IGNORECASE)
        if len(blocks) >= 2: break

    for block in blocks:
        def extract(pats):
            for p in pats:
                m = re.search(p, block, re.DOTALL|re.IGNORECASE)
                if m: return clean_text(re.sub(r"<[^>]+>","",m.group(1)))
            return ""
        name = extract([r'class="[^"]*(?:name|titolo|denominazione|insegna)[^"]*"[^>]*>(.*?)</',r'<h[1-3][^>]*>(.*?)</h[1-3]>'])
        if not name: continue
        phone   = clean_phone(extract([r'class="[^"]*(?:phone|tel)[^"]*"[^>]*>(.*?)</',r'href="tel:([^"]+)"']))
        address = extract([r'class="[^"]*(?:address|indirizzo)[^"]*"[^>]*>(.*?)</'])
        cat     = extract([r'class="[^"]*(?:category|categoria)[^"]*"[^>]*>(.*?)</']) or what
        em_m    = re.search(r'[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}', block)
        web_m   = re.search(r'href="(https?://(?!(?:www\.)?paginegialle\.it)[^"]+)"', block)
        listings.append({
            "id":"","name":name,"subtitle":"","description":"","category":cat,
            "phone":phone,"email":em_m.group(0) if em_m else "","website":web_m.group(1) if web_m else "",
            "address":address,"city":where,"province":"","postalCode":"",
            "latitude":None,"longitude":None,"rating":None,"reviewCount":None,
            "image":"","facebook":"","instagram":"","searchWhat":what,"searchWhere":where,"sourceUrl":"",
        })

    total_m = re.search(r'"(?:total|totalCount|numResults)"\s*:\s*(\d+)', html)
    return {"listings": listings, "total_count": int(total_m.group(1)) if total_m else len(listings)}
