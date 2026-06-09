# PagineGialle.it Business Scraper

Extract structured business listings from PagineGialle.it, one of the main Italian online directories for local businesses, professionals, shops, services, and companies.

This Apify Actor is built for users who need Italian business data for lead generation, local market research, sales prospecting, CRM enrichment, competitor mapping, and B2B data collection.

No coding required. Select business categories and Italian cities, run the Actor, and export the results as JSON, CSV, or Excel.

## What this Actor does

The Actor searches PagineGialle.it by business category and city, then extracts structured business listings from public search result pages.

Example searches:

- restaurants in Rome
- dentists in Milan
- lawyers in Naples
- plumbers in Turin
- hotels in Florence
- pharmacies in Bologna

You can combine multiple categories and multiple cities in one run.

Example: 3 categories x 5 cities = 15 automatic searches.

## Main use cases

### B2B lead generation

Build targeted prospect lists by industry and location.

Examples:

- restaurants in Milan
- dentists in Rome
- gyms in Naples
- real estate agencies in Turin
- lawyers in Bologna

Useful for sales teams, agencies, consultants, and local service providers.

### Sales prospecting

Collect business names, phone numbers, addresses, categories, ratings, and profile URLs to support outbound sales workflows.

Good for:

- cold calling
- local outreach
- partnership research
- agency prospecting
- offline-to-online sales targeting

### Local SEO research

Analyze the presence of local businesses in specific cities and categories.

Useful for:

- SEO agencies
- digital marketing consultants
- local ranking research
- competitor mapping
- niche discovery

### Market research

Estimate how many businesses are active in a category and compare local competition between cities.

Examples:

- number of dentists in Rome vs Milan
- density of gyms in major Italian cities
- restaurant competition by city
- service availability in specific regions

### CRM enrichment

Use extracted public listings to enrich internal CRM records with additional public business information.

Potentially useful fields:

- business name
- business category
- address
- phone number
- city
- rating
- profile URL

### Data analysis and business intelligence

Export the dataset and analyze it with spreadsheets, BI tools, Python, SQL, or CRM platforms.

Possible analysis:

- businesses by category
- businesses by city
- average rating by sector
- local competition mapping
- phone availability by industry
- lead segmentation by area

## Extracted data

The Actor extracts structured data from public search result listings.

| Field | Description |
|---|---|
| `id` | Internal listing identifier when available |
| `name` | Business name |
| `category` | Business category shown in the listing |
| `phone` | Public phone number when available |
| `address` | Business address |
| `city` | Search city |
| `rating` | Public rating when available |
| `reviewCount` | Review count when available |
| `imageUrl` | Listing image URL when available |
| `profileUrl` | Public PagineGialle.it profile URL |
| `searchCategory` | Category used for the search |
| `searchCity` | City used for the search |
| `searchUrl` | Search URL used by the Actor |
| `source` | Source website name |
| `scrapedAt` | ISO timestamp of the extraction |

Some fields such as `email`, `website`, `province`, `postalCode`, `latitude`, `longitude`, `facebook`, and `instagram` may be present in the output for schema compatibility, but they can be empty depending on what is publicly visible and on the current extraction level.

This Actor is currently strongest for local business discovery, phone-based outreach, address collection, and profile URL extraction. It should not be marketed as a guaranteed email scraper.

## Input options

### Business categories

Select one or more predefined business categories from the dropdown.

You can also add custom categories manually.

### Cities

Select one or more Italian cities from the dropdown.

You can also add custom cities manually.

### Max results per search

Set the maximum number of listings to collect for each category and city combination.

Example:

- `200` results for restaurants in Rome
- `500` results for dentists in Milan
- `1000` results for hotels across multiple Italian cities

### Output filters

Optional filters:

- only listings with phone number
- only listings with website
- only listings with email

Important: website and email availability depends on what is publicly visible and on the extraction level. If you enable strict email or website filters and those fields are not available in search results, the run may return fewer results or zero results.

### Proxy settings

Apify Proxy is recommended for larger multi-city and multi-category runs.

### Advanced raw search queries

Advanced users can provide custom search combinations using JSON:

```json
[
  { "what": "ristorante", "where": "roma" },
  { "what": "dentista", "where": "milano" },
  { "what": "avvocato", "where": "napoli" }
]
```

When raw search queries are provided, they override dropdown category and city selections.

## Output formats

Results can be exported from the Apify dataset as:

- JSON
- CSV
- Excel

This makes the Actor suitable for:

- spreadsheets
- CRMs
- lead generation workflows
- data pipelines
- BI dashboards
- custom analytics scripts

## Categories: Italian and English

| Italian category | English translation |
|---|---|
| `ristorante` | Restaurant |
| `pizzeria` | Pizzeria |
| `bar` | Bar / Cafe |
| `pasticceria` | Pastry shop |
| `gelateria` | Ice cream shop |
| `trattoria` | Trattoria |
| `enoteca` | Wine bar |
| `sushi` | Sushi restaurant |
| `dentista` | Dentist |
| `medico` | Doctor / GP |
| `farmacia` | Pharmacy |
| `parrucchiere` | Hair salon |
| `estetista` | Beauty salon |
| `fisioterapista` | Physiotherapist |
| `psicologo` | Psychologist |
| `ottico` | Optician |
| `veterinario` | Veterinarian |
| `avvocato` | Lawyer |
| `commercialista` | Accountant |
| `notaio` | Notary |
| `architetto` | Architect |
| `geometra` | Surveyor |
| `agenzia-immobiliare` | Real estate agency |
| `agenzia-assicurativa` | Insurance agency |
| `idraulico` | Plumber |
| `elettricista` | Electrician |
| `falegname` | Carpenter |
| `muratore` | Builder / Mason |
| `impresa-edile` | Construction company |
| `officina-meccanica` | Auto repair shop |
| `carrozzeria` | Body shop |
| `hotel` | Hotel |
| `bed-and-breakfast` | Bed & Breakfast |
| `agriturismo` | Farm stay / Agriturismo |
| `palestra` | Gym / Fitness center |
| `piscina` | Swimming pool |
| `scuola-guida` | Driving school |
| `supermercato` | Supermarket |
| `ferramenta` | Hardware store |
| `fiorista` | Florist |
| `panificio` | Bakery |

## Supported cities

The Actor includes predefined major Italian cities such as:

- Rome
- Milan
- Naples
- Turin
- Bologna
- Florence
- Palermo
- Genoa
- Venice
- Bari
- Catania
- Verona
- Padua
- Trieste
- Brescia
- Lecce
- Rimini
- Reggio Calabria

Custom Italian cities can also be added manually.

## Example searches

### Restaurants in Rome

```json
[
  { "what": "ristorante", "where": "roma" }
]
```

### Dentists in Milan

```json
[
  { "what": "dentista", "where": "milano" }
]
```

### Lawyers across multiple cities

```json
[
  { "what": "avvocato", "where": "roma" },
  { "what": "avvocato", "where": "milano" },
  { "what": "avvocato", "where": "napoli" },
  { "what": "avvocato", "where": "torino" }
]
```

### Custom niche search

```json
[
  { "what": "tatuaggi", "where": "roma" },
  { "what": "pompe-funebri", "where": "milano" },
  { "what": "erboristeria", "where": "bologna" }
]
```

## Example output

```json
{
  "name": "Example Business Name",
  "category": "Restaurant",
  "phone": "+39 06 0000000",
  "address": "Via Example 10",
  "city": "roma",
  "rating": 4.5,
  "profileUrl": "https://www.paginegialle.it/example-business",
  "searchCategory": "ristorante",
  "searchCity": "roma",
  "source": "paginegialle.it",
  "scrapedAt": "2026-06-09T12:00:00.000Z"
}
```

## Technical details

This Actor is built with:

- Node.js
- Apify SDK
- Crawlee
- HTTP crawling
- Cheerio HTML parsing
- Apify Dataset export

The scraper builds search URLs from selected categories and cities, normalizes Italian slugs, handles common plural-to-singular category aliases, crawls result pages, extracts listing cards, removes duplicates, and saves structured records to the Apify dataset.

For larger cities, the Actor can also crawl district-level result pages to collect more listings beyond the first result pages.

## Why use this Actor

- No coding required
- Works with predefined and custom categories
- Supports predefined and custom Italian cities
- Exports to JSON, CSV, and Excel
- Suitable for lead generation and market research
- Built for repeatable Apify workflows
- Useful for Italian local business datasets

## Recommended usage

For small tests:

- 1 category
- 1 city
- 50 to 200 results

For production runs:

- multiple categories
- multiple cities
- Apify Proxy enabled
- reasonable max results per search
- export to CSV or Excel

For large-scale lead generation:

- run by region or city group
- split large jobs into multiple runs
- deduplicate results after export
- validate data before outreach

## Data quality notes

Data availability depends on what is publicly visible on PagineGialle.it.

Phone numbers are commonly available, while other fields may vary depending on the listing.

Some listings may have incomplete data, duplicate business names, missing ratings, or generic category labels. Always validate important records before using them in sales, marketing, or CRM workflows.

## Legal and compliance note

This Actor extracts publicly available business listing information.

Users are responsible for using the extracted data in compliance with applicable laws and regulations, including GDPR, privacy rules, platform terms, and anti-spam regulations.

Do not use extracted data for unlawful, abusive, deceptive, or non-compliant outreach.

## Best for

- B2B lead generation
- Italian business directories
- Local SEO research
- Sales prospecting
- CRM enrichment
- Market research
- Competitor analysis
- Local business intelligence
