# PagineGialle.it Business Directory Scraper

Extract structured public business listings from PagineGialle.it, one of Italy's main online directories for companies, professionals, local shops, restaurants, services, and public-facing business profiles.

This Apify Actor lets you search Italian businesses by category and city, collect directory listing data, and export the results as JSON, CSV, or Excel.

It is designed for market research, local business mapping, sales preparation, competitor analysis, CRM preparation, and structured directory data collection.

## What this Actor does

The Actor searches PagineGialle.it using business categories and Italian cities, then extracts structured data from public directory result pages.

Typical searches include:

- construction companies in Bari
- accountants in Milan
- notaries in Turin
- pastry shops in Rome
- Japanese restaurants in Naples
- doctors in Bologna
- wine shops in Florence

You can run a single category and city, or combine multiple categories and multiple cities in one run.

Example:

```text
7 categories x 3 cities = 21 automatic searches
```

## Main use cases

### Italian business directory data collection

Collect structured information from PagineGialle.it listings and turn public directory pages into usable datasets.

Useful for:

- business directories
- local datasets
- regional company lists
- category-based company research
- Italian market databases

### Local market research

Analyze which businesses are present in specific cities and sectors.

Examples:

- how many accountants are listed in Bari
- how many pastry shops are listed in Milan
- how many medical practices are listed in Turin
- which local areas contain more construction companies
- which business categories are more visible in a city

### Competitor and territory mapping

Map local competitors, business density, and local service coverage by category and city.

Useful for agencies, consultants, franchising research, local sales teams, and companies planning expansion in Italy.

### Sales and CRM preparation

Create structured business lists before starting manual verification, CRM imports, phone-based workflows, or local business research.

The Actor can collect public business names, phone numbers, addresses, profile URLs, available websites, and available contact links when present in the directory listing.

### Local SEO and digital presence research

Analyze local business visibility and compare listings across industries and cities.

Useful for:

- SEO agencies
- local marketing agencies
- web agencies
- consultants selling websites or digital services
- local visibility analysis

### Data analysis and BI workflows

Export the dataset and analyze it in spreadsheets, SQL databases, Python scripts, CRM systems, or BI tools.

Possible analysis:

- businesses by city
- businesses by category
- phone availability
- website availability
- contact link availability
- business profile coverage
- local competitor density

## Extracted data

The Actor extracts structured fields from public PagineGialle.it search result listings.

| Field | Description |
|---|---|
| `id` | Listing identifier when available |
| `name` | Business or professional name |
| `category` | Category associated with the listing/search |
| `phone` | Public phone number when available |
| `email` | Email field, if publicly available in the listing data; often empty |
| `website` | Business website when available and detected as a real external website |
| `contactUrl` | Best available external contact link, such as website or WhatsApp |
| `whatsappUrl` | WhatsApp contact link when available |
| `address` | Business address or location text |
| `city` | Search city |
| `province` | Province field when available |
| `postalCode` | Postal code field when available |
| `latitude` | Latitude when available |
| `longitude` | Longitude when available |
| `rating` | Public rating when available |
| `reviewCount` | Review count when available |
| `imageUrl` | Listing image URL when available |
| `facebook` | Facebook URL when available |
| `instagram` | Instagram URL when available |
| `profileUrl` | Public PagineGialle.it profile URL |
| `searchCategory` | Category used for the search |
| `searchCity` | City used for the search |
| `searchUrl` | Search URL used by the Actor |
| `source` | Source website name |
| `scrapedAt` | ISO timestamp of the extraction |

Data availability depends on what is publicly visible in PagineGialle.it result pages. Phone numbers are often available. Websites, WhatsApp links, ratings, images, and other fields depend on the individual listing.

## Product positioning

This is a PagineGialle.it business directory scraper.

It is not positioned as a guaranteed email extraction tool or as a full company intelligence provider. The main value is collecting structured public business directory listings by category and city.

## Input options

### Categories

Select one or more business categories from the input dropdown, or provide custom categories manually.

Examples:

- `impresa-edile`
- `commercialista`
- `notaio`
- `trattoria`
- `pasticceria`
- `sushi`
- `medico`
- `gelateria`
- `enoteca`

### Cities

Select one or more Italian cities from the dropdown, or provide custom cities manually.

Examples:

- `bari`
- `milano`
- `torino`
- `roma`
- `napoli`
- `bologna`
- `firenze`

### Max results

Set the maximum number of records to collect for each category and city combination.

Examples:

- `100` for a quick test
- `500` for medium runs
- `2000` for larger category/city runs

### Filters

Optional filters are available:

- only listings with phone number
- only listings with website
- only listings with email

Use filters carefully. If a strict filter is enabled and the selected field is not commonly available for that category, the run can return fewer results.

### Proxy

Apify Proxy is recommended for larger runs, multiple cities, and multiple categories.

### Advanced search input

Advanced users can provide raw search combinations:

```json
[
  { "what": "commercialista", "where": "bari" },
  { "what": "notaio", "where": "milano" },
  { "what": "impresa-edile", "where": "torino" }
]
```

When advanced searches are provided, they override the standard category/city dropdown combinations.

## Output formats

Results are saved to the default Apify dataset and can be exported as:

- JSON
- CSV
- Excel
- XML
- RSS
- HTML

The most common formats for business workflows are CSV and Excel.

## Example input

```json
{
  "categories": [
    "commercialista",
    "notaio",
    "impresa-edile"
  ],
  "cities": [
    "bari",
    "milano",
    "torino"
  ],
  "maxResults": 500,
  "onlyWithEmail": false,
  "onlyWithPhone": false,
  "onlyWithWebsite": false,
  "useApifyProxy": true,
  "customCategories": [],
  "customCities": [],
  "searches": []
}
```

## Example output

```json
{
  "id": "dfb3328c-2b7f-4715-a79f-ca2f52c3806a",
  "name": "Example Business Name",
  "category": "commercialista",
  "phone": "080 0000000",
  "email": "",
  "website": "https://www.example-business.it",
  "contactUrl": "https://www.example-business.it",
  "whatsappUrl": "",
  "address": "Via Example, 10 - 70100 Bari (BA)",
  "city": "bari",
  "rating": 4.5,
  "profileUrl": "https://www.paginegialle.it/example-business",
  "searchCategory": "commercialista",
  "searchCity": "bari",
  "searchUrl": "https://www.paginegialle.it/ricerca/commercialisti/bari",
  "source": "paginegialle.it",
  "scrapedAt": "2026-06-09T17:12:06.240Z"
}
```

## Category examples: Italian to English

| Italian category | English meaning |
|---|---|
| `impresa-edile` | Construction company |
| `commercialista` | Accountant / tax consultant |
| `notaio` | Notary |
| `trattoria` | Trattoria / restaurant |
| `pasticceria` | Pastry shop |
| `sushi` | Sushi / Japanese restaurant |
| `medico` | Doctor / medical practice |
| `gelateria` | Ice cream shop |
| `enoteca` | Wine shop / wine bar |
| `ristorante` | Restaurant |
| `pizzeria` | Pizzeria |
| `bar` | Bar / cafe |
| `dentista` | Dentist |
| `farmacia` | Pharmacy |
| `parrucchiere` | Hair salon |
| `estetista` | Beauty salon |
| `fisioterapista` | Physiotherapist |
| `psicologo` | Psychologist |
| `ottico` | Optician |
| `veterinario` | Veterinarian |
| `avvocato` | Lawyer |
| `architetto` | Architect |
| `geometra` | Surveyor |
| `agenzia-immobiliare` | Real estate agency |
| `agenzia-assicurativa` | Insurance agency |
| `idraulico` | Plumber |
| `elettricista` | Electrician |
| `falegname` | Carpenter |
| `muratore` | Builder / mason |
| `officina-meccanica` | Auto repair shop |
| `carrozzeria` | Body shop |
| `hotel` | Hotel |
| `bed-and-breakfast` | Bed & Breakfast |
| `agriturismo` | Farm stay / agriturismo |
| `palestra` | Gym / fitness center |
| `piscina` | Swimming pool |
| `scuola-guida` | Driving school |
| `supermercato` | Supermarket |
| `ferramenta` | Hardware store |
| `fiorista` | Florist |
| `panificio` | Bakery |

## Supported cities

The Actor includes many predefined Italian cities, including:

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
- Taranto
- Lecce
- Rimini
- Reggio Calabria

Custom cities can also be added manually.

## Technical details

The Actor is built with:

- Node.js
- Apify SDK
- Crawlee
- HTTP crawling
- Cheerio HTML parsing
- Apify Dataset export

Technical workflow:

1. Builds PagineGialle.it search URLs from category and city inputs.
2. Normalizes category and city slugs.
3. Handles known Italian category aliases and public directory slugs.
4. Crawls the first result pages.
5. Detects district-level result pages when available.
6. Crawls district result pages to collect more listings.
7. Extracts structured listing cards.
8. Separates real websites from WhatsApp contact links.
9. Deduplicates records within each category/city run.
10. Saves results to the Apify dataset.

## Performance notes

For small tests, use:

- 1 category
- 1 city
- 50 to 100 max results

For medium runs, use:

- 3 to 10 categories
- 1 to 5 cities
- 100 to 1000 max results
- Apify Proxy enabled

For larger runs:

- split jobs by region or city group
- keep max results reasonable
- export and deduplicate after the run if needed
- validate important records manually before operational use

## Data quality notes

PagineGialle.it listings vary by category, city, and individual business profile.

Some records may have complete phone and address data. Others may contain only partial information. Website and WhatsApp contact links are only available when visible in the public listing data.

A business can appear in more than one category or district result page. The Actor deduplicates records within each search run, but external post-processing can still be useful for large multi-category exports.

## Responsible use

This Actor extracts publicly available business directory listing information.

Users are responsible for using the extracted data in compliance with applicable laws, regulations, privacy rules, and platform terms.

## Best for

- PagineGialle.it scraping
- Italian business directory datasets
- Local business data collection
- Market research in Italy
- Business category mapping
- City-level competitor analysis
- CRM preparation
- Local SEO research
- Sales list preparation
- Public directory data extraction

## Not designed for

- guaranteed email extraction
- private data extraction
- full company intelligence enrichment
- operational decision-making without manual validation

## Summary

PagineGialle.it Business Directory Scraper is a practical Actor for collecting structured public Italian business listings by category and city.

It helps transform PagineGialle.it search results into clean datasets that can be exported, filtered, analyzed, and used in business research workflows.
