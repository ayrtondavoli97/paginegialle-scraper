import { Actor } from 'apify';
import { HttpCrawler } from 'crawlee';
import * as cheerio from 'cheerio';

const BASE_URL = 'https://www.paginegialle.it';


// PagineGialle category slug aliases (plural -> singular form used by the site)
const SLUG_ALIASES = {
    'avvocati':            'avvocato',
    'idraulici':           'idraulico',
    'parrucchieri':        'parrucchiere',
    'farmacie':            'farmacia',
    'commercialisti':      'commercialista',
    'agenzie-immobiliari': 'agenzia-immobiliare',
    'officine-meccaniche': 'officina-meccanica',
    'dentisti':            'dentista',
    'medici':              'medico',
    'elettricisti':        'elettricista',
    'fisioterapisti':      'fisioterapista',
    'veterinari':          'veterinario',
    'notai':               'notaio',
    'architetti':          'architetto',
    'geometri':            'geometra',
    'psicologi':           'psicologo',
};

function normalizeSlug(text) {
    return String(text || '').toLowerCase().trim()
        .replace(/[\s_/]+/g, '-')
        .replace(/[àáâãäå]/g, 'a').replace(/[èéêë]/g, 'e')
        .replace(/[ìíîï]/g, 'i').replace(/[òóôõö]/g, 'o').replace(/[ùúûü]/g, 'u')
        .replace(/[^a-z0-9-]/g, '').replace(/-+/g, '-').replace(/^-|-$/g, '');
}

function resolveWhatSlug(what) {
    const raw = String(what || '').toLowerCase().trim();
    const normalized = normalizeSlug(what);
    return SLUG_ALIASES[raw] ?? SLUG_ALIASES[normalized] ?? normalized;
}

function buildUrl(what, where, page = 1) {
    // Apply alias (avvocati -> avvocato, idraulici -> idraulico, etc.)
    const resolved = resolveWhatSlug(what);
    const base = `${BASE_URL}/ricerca/${resolved}/${normalizeSlug(where)}`;
    return page > 1 ? `${base}?pg=${page}` : base;
}

function absoluteUrl(url) {
    if (!url) return '';
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    if (url.startsWith('//')) return `https:${url}`;
    if (url.startsWith('/')) return `${BASE_URL}${url}`;
    return url;
}

function cleanText(str) {
    if (!str) return '';
    return String(str).replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function cleanPhone(str) {
    if (!str) return '';
    return String(str).replace(/[^\d\s+()-]/g, '').trim();
}

function extractTotalCount(html) {
    const m = html.match(/QTA=(\d+)/);
    return m ? parseInt(m[1]) : 0;
}

function extractDistrictUrls(html, whatSlug, whereSlug) {
    const $ = cheerio.load(html);
    const urls = new Set();
    const base = `${BASE_URL}/ricerca/${whatSlug}/`;
    const baseCity = `${base}${whereSlug}`.toLowerCase();
    $('a.chip').each((_, el) => {
        const href = absoluteUrl($(el).attr('href') || '');
        if (href.startsWith(base) && !href.includes('?') && !href.includes('#')
            && href.toLowerCase() !== baseCity) {
            urls.add(href);
        }
    });
    return [...urls];
}

const BADGE_WORDS = new Set(['suggerito','consigliato','sponsor','in evidenza','verificato','aperto','chiuso']);
const SKIP_WORDS = ['più di','risultati fuori','ricerche correlate','risultati per','annunci correlati'];

function makeDedupeKey(item) {
    if (item.id) return `id:${item.id}`;
    return [item.name, item.address, item.phone, item.searchCity]
        .map(v => cleanText(v).toLowerCase())
        .filter(Boolean)
        .join('|');
}

function parseListings(html, what, where, searchUrl = '', scrapedAt = '') {
    const $ = cheerio.load(html);
    const listings = [];

    $('[class*="card-listing"]').each((_, card) => {
        const $c = $(card);
        const name = cleanText($c.find('[class*="search-itm__rag"]').first().text());
        if (!name) return;
        if (SKIP_WORDS.some(w => name.toLowerCase().includes(w))) return;

        const id = $c.attr('data-user') || '';

        let sourceUrl = '';
        $c.find('a[href]').each((_, a) => {
            const h = absoluteUrl($(a).attr('href') || '');
            if (h.includes('paginegialle.it/') && !/\/(mappa|profilo|ricerca|static|servizi|shop|news|scheda)\//.test(h)) {
                sourceUrl = h; return false;
            }
        });

        const phones = [];
        $c.find('[class*="search-itm__phone-item"]').each((_, el) => {
            const p = cleanPhone($(el).text());
            if (p) phones.push(p);
        });

        const address = cleanText($c.find('[class*="search-itm__adr"] div').first().text());

        let rating = null;
        const rc = $c.find('[class*="rating-stars--"]').first().attr('class') || '';
        const rm = rc.match(/rating-stars--(\d+)/);
        if (rm) { const v = parseInt(rm[1]); if (v > 5) rating = Math.round(v / 20 * 10) / 10; }

        let category = what;
        const lbl = cleanText($c.find('[class*="search-itm__label"]').first().text());
        if (lbl && !BADGE_WORDS.has(lbl.toLowerCase())) category = lbl;

        const image = absoluteUrl($c.find('img[src]').first().attr('src') || '');

        let email = '';
        let website = '';
        $c.find('a[href]').each((_, a) => {
            const href = $(a).attr('href') || '';
            const absoluteHref = absoluteUrl(href);
            if (!email && href.startsWith('mailto:')) {
                email = href.replace(/^mailto:/i, '').split('?')[0].trim();
            }
            if (!website && absoluteHref.startsWith('http')
                && !absoluteHref.includes('paginegialle.it')
                && !absoluteHref.includes('google.')
                && !absoluteHref.includes('facebook.com')
                && !absoluteHref.includes('instagram.com')) {
                website = absoluteHref;
            }
        });

        listings.push({
            id,
            name,
            category,
            phone:          phones[0] || '',
            email,
            website,
            address,
            city:           where,
            province:       '',
            postalCode:     '',
            latitude:       null,
            longitude:      null,
            rating,
            reviewCount:    null,
            imageUrl:       image,
            facebook:       '',
            instagram:      '',
            profileUrl:     sourceUrl,
            searchCategory: what,
            searchCity:     where,
            searchUrl,
            source:         'paginegialle.it',
            scrapedAt,
        });
    });

    return listings;
}

// -- Main --------------------------------------------------------------------
await Actor.init();

const input = await Actor.getInput() ?? {};
const maxResults = input.maxResults ?? 200;
const useProxy   = input.useApifyProxy !== false;
const onlyWithPhone = input.onlyWithPhone === true;
const onlyWithWebsite = input.onlyWithWebsite === true;
const onlyWithEmail = input.onlyWithEmail === true;
const runStartedAt = new Date().toISOString();

// Build searches from categories x cities dropdowns, or use custom searches array
const manualSearches = (input.searches ?? []).filter(s => s.what && s.where);
let searches = [];

if (manualSearches.length === 0) {
    // Use dropdown selections
    const cats    = [...(input.categories ?? ['ristorante']), ...(input.customCategories ?? [])];
    const cityArr = [...(input.cities ?? ['roma']), ...(input.customCities ?? [])];
    for (const what of cats) {
        for (const where of cityArr) {
            searches.push({ what, where });
        }
    }
    console.log(`Built ${searches.length} searches from ${cats.length} categories x ${cityArr.length} cities`);
} else {
    // Use manual searches from Advanced field; aliases still apply while building URLs.
    searches = manualSearches;
    console.log(`Using ${searches.length} manual search queries`);
}

if (!searches.length) { console.error('No searches defined'); await Actor.exit(); }

let proxyConfiguration;
if (useProxy) {
    proxyConfiguration = await Actor.createProxyConfiguration();
    console.log('Proxy configured');
} else {
    console.log('Direct connection');
}

const dataset = await Actor.openDataset();
let totalSaved = 0;

for (let si = 0; si < searches.length; si++) {
    const { what, where } = searches[si];
    if (!what || !where) continue;

    console.log(`\n[${si+1}/${searches.length}] '${what}' in '${where}'`);

    const whatSlug  = resolveWhatSlug(what);
    const whereSlug = normalizeSlug(where);
    const results   = [];
    const seenIds   = new Set();
    let districtUrls = [];
    let page1Html    = '';

    // Step 1: page 1 + 2 (with direct fallback if proxy gives 0)
    let proxyForStep1 = proxyConfiguration;
    await new Promise(resolve => {
        const crawler = new HttpCrawler({
            proxyConfiguration: proxyForStep1,
            maxConcurrency: 2,
            async requestHandler({ body, request }) {
                const html = body.toString();
                const lbl  = request.label;

                if (lbl === 'P1') {
                    page1Html = html;
                    console.log(`  Total count: ${extractTotalCount(html)}`);
                }

                const listings = parseListings(html, what, where, request.url, runStartedAt);
                let newCount = 0;
                for (const item of listings) {
                    const uid = makeDedupeKey(item);
                    if (uid && !seenIds.has(uid)) { seenIds.add(uid); results.push(item); newCount++; }
                }
                console.log(`  Page ${lbl === 'P1' ? 1 : 2}: ${newCount} new`);

                if (lbl === 'P1' && page1Html) {
                    districtUrls = extractDistrictUrls(page1Html, whatSlug, whereSlug);
                    console.log(`  Districts: ${districtUrls.length} found`);
                }
            },
            failedRequestHandler({ request, error }) {
                console.warn(`  Failed: ${request.url} - ${error.message}`);
                if (request.label === 'P2') {
                    districtUrls = extractDistrictUrls(page1Html, whatSlug, whereSlug);
                }
            },
        });
        crawler.run([
            { url: buildUrl(what, where, 1), label: 'P1', uniqueKey: `p1-${what}-${where}` },
            { url: buildUrl(what, where, 2), label: 'P2', uniqueKey: `p2-${what}-${where}` },
        ]).then(resolve);
    });

    // If proxy gave 0 results, retry step1 without proxy (direct connection)
    if (results.length === 0 && proxyConfiguration) {
        console.log(`  Proxy gave 0 results - retrying direct...`);
        page1Html = '';
        districtUrls = [];
        await new Promise(resolve => {
            const crawler = new HttpCrawler({
                maxConcurrency: 2,
                async requestHandler({ body, request }) {
                    const html = body.toString();
                    const lbl  = request.label;
                    if (lbl === 'P1') {
                        page1Html = html;
                        console.log(`  Direct total: ${extractTotalCount(html)}`);
                    }
                    const listings = parseListings(html, what, where, request.url, runStartedAt);
                    let newCount = 0;
                    for (const item of listings) {
                        const uid = makeDedupeKey(item);
                        if (uid && !seenIds.has(uid)) { seenIds.add(uid); results.push(item); newCount++; }
                    }
                    console.log(`  Direct page ${lbl === 'P1' ? 1 : 2}: ${newCount} new`);
                    if (lbl === 'P1' && page1Html) {
                        districtUrls = extractDistrictUrls(page1Html, whatSlug, whereSlug);
                        console.log(`  Direct districts: ${districtUrls.length}`);
                    }
                },
                failedRequestHandler({ request, error }) {
                    console.warn(`  Direct failed: ${request.url} - ${error.message}`);
                },
            });
            crawler.run([
                { url: buildUrl(what, where, 1), label: 'P1', uniqueKey: `dp1-${what}-${where}` },
                { url: buildUrl(what, where, 2), label: 'P2', uniqueKey: `dp2-${what}-${where}` },
            ]).then(resolve);
        });
    }

    // Step 2: districts (concurrent, proxy rotates IPs)
    if (districtUrls.length > 0 && results.length < maxResults) {
        const needed = maxResults - results.length;
        console.log(`  Crawling up to ${Math.min(districtUrls.length, 200)} districts (need ${needed} more)...`);

        await new Promise(resolve => {
            const crawler = new HttpCrawler({
                proxyConfiguration,
                maxConcurrency: 10,
                maxRequestsPerMinute: 120,
                async requestHandler({ body, request }) {
                    if (results.length >= maxResults) return;
                    const listings = parseListings(body.toString(), what, where, request.url, runStartedAt);
                    for (const item of listings) {
                        const uid = makeDedupeKey(item);
                        if (uid && !seenIds.has(uid)) { seenIds.add(uid); results.push(item); }
                    }
                },
                failedRequestHandler() {},
            });
            crawler.run(
                districtUrls.slice(0, 200).map((url, i) => ({
                    url,
                    uniqueKey: `dist-${what}-${where}-${i}`,
                }))
            ).then(resolve);
        });

        console.log(`  Districts done: ${results.length} total results`);
    }

    let filteredResults = results;
    if (onlyWithPhone) filteredResults = filteredResults.filter(item => item.phone);
    if (onlyWithWebsite) filteredResults = filteredResults.filter(item => item.website);
    if (onlyWithEmail) filteredResults = filteredResults.filter(item => item.email);

    const toSave = filteredResults.slice(0, maxResults);
    if (toSave.length > 0) {
        await dataset.pushData(toSave);
        totalSaved += toSave.length;
        console.log(`  Saved ${toSave.length} | grand total: ${totalSaved}`);
    } else {
        console.warn(`  0 results for '${what}'/'${where}' after filters`);
    }
}

console.log(`\nDone. Total saved: ${totalSaved}`);
await Actor.exit();
