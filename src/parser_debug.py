"""
Standalone parser test — run locally with a saved HTML file:
  python3 -m src.parser_debug path/to/raw.html
"""
import sys, json, re
from .utils import clean_phone, clean_text

def analyze_html(html: str):
    print(f"=== HTML size: {len(html)} chars ===\n")

    # 1. Check for __NEXT_DATA__
    nd = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    print(f"__NEXT_DATA__: {'FOUND' if nd else 'NOT FOUND'}")
    if nd:
        try:
            data = json.loads(nd.group(1))
            print(f"  Keys: {list(data.keys())[:10]}")
        except Exception as e:
            print(f"  Parse error: {e}")

    # 2. Check window.* state objects
    for varname in ["__PG_PROPS__", "__INITIAL_STATE__", "__STATE__", "pg", "initialState"]:
        m = re.search(rf'window\.{re.escape(varname)}\s*=\s*({{.+?}});', html, re.DOTALL)
        print(f"window.{varname}: {'FOUND' if m else 'not found'}")

    # 3. Count script tags
    scripts = re.findall(r'<script[^>]*>', html, re.IGNORECASE)
    print(f"\nScript tags: {len(scripts)}")

    # 4. Check JSON-LD
    jld = re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL|re.IGNORECASE)
    print(f"JSON-LD blocks: {len(jld)}")
    for i, block in enumerate(jld[:3]):
        try:
            d = json.loads(block.strip())
            t = d.get("@type","") if isinstance(d,dict) else type(d).__name__
            print(f"  [{i}] @type={t} keys={list(d.keys())[:6] if isinstance(d,dict) else '?'}")
        except Exception as e:
            print(f"  [{i}] parse error: {e}")

    # 5. Look for listing-like patterns
    print("\n=== Class names containing 'listing' or 'result' or 'card' or 'item' ===")
    classes = set(re.findall(r'class="([^"]*(?:listing|result|card|item|company|aziend)[^"]*)"', html, re.IGNORECASE))
    for c in sorted(classes)[:20]:
        print(f"  {c}")

    # 6. Look for data-* attributes that could be IDs
    data_attrs = set(re.findall(r'(data-(?:cid|id|listing|business|pg|ent)[^=\s]*)', html, re.IGNORECASE))
    print(f"\ndata-* attributes: {sorted(data_attrs)[:15]}")

    # 7. Sample h2/h3 tags (these were wrongly extracted)
    headings = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL|re.IGNORECASE)
    print(f"\nH2/H3 tags ({len(headings)} total, first 10):")
    for h in headings[:10]:
        print(f"  {clean_text(re.sub(r'<[^>]+>','',h))[:80]}")

    # 8. Look for phone patterns
    phones = re.findall(r'(?:href="tel:|>)(\+?[\d\s\-\(\)]{8,15})', html)
    print(f"\nPhone patterns found: {len(phones)}, sample: {phones[:5]}")

    # 9. Look for inline JSON arrays
    print("\n=== Inline JSON arrays with 'name' field ===")
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        script = m.group(1)
        if '"name"' in script and len(script) > 200:
            arr = re.search(r'(\[\s*\{.+?"name".+?\}\s*\])', script, re.DOTALL)
            if arr:
                try:
                    items = json.loads(arr.group(1))
                    if isinstance(items, list) and len(items) > 1:
                        print(f"  Found array: {len(items)} items, keys={list(items[0].keys())[:8]}")
                except Exception:
                    pass

    # 10. Print first 3000 chars to see structure
    print("\n=== First 3000 chars ===")
    print(html[:3000])


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python3 -m src.parser_debug path/to/raw.html")
        sys.exit(1)
    with open(path, encoding="utf-8", errors="replace") as f:
        html = f.read()
    analyze_html(html)
