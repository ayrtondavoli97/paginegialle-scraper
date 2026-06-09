# PagineGialle.it — Italian Yellow Pages Business Scraper

Extract structured business data from **PagineGialle.it**, Italy's #1 Yellow Pages directory with over 3 million monthly visits.

## What you get

| Field | Description |
|---|---|
| `name` | Business name |
| `category` | Business category |
| `phone` | Phone number |
| `email` | Email address (when listed) |
| `website` | Website URL |
| `address` | Street address |
| `city` | City |
| `province` | Province/region |
| `postalCode` | ZIP/postal code |
| `latitude` / `longitude` | GPS coordinates |
| `rating` | Average customer rating |
| `reviewCount` | Number of reviews |
| `facebook` | Facebook page URL |
| `instagram` | Instagram profile URL |
| `searchWhat` | Your original search category |
| `searchWhere` | Your original search location |

## Use Cases

- **B2B Lead Generation** — Build targeted lists of Italian businesses by category and city
- **Sales Prospecting** — Extract phones and emails for outreach campaigns
- **Market Research** — Analyze competitor density, ratings, and coverage by area
- **CRM Enrichment** — Enrich existing records with contact data and coordinates
- **Local SEO Analysis** — Map businesses per category across Italian cities

## Input Example

```json
{
  "searches": [
    { "what": "ristoranti", "where": "napoli" },
    { "what": "avvocati", "where": "milano" },
    { "what": "idraulici", "where": "roma" }
  ],
  "maxResults": 500,
  "onlyWithPhone": true,
  "useApifyProxy": true,
  "proxyCountry": "IT"
}
```

## Popular Categories (`what`)

`ristoranti` · `pizzerie` · `bar-caffe` · `medici` · `dentisti` · `farmacie` · `parrucchieri` · `avvocati` · `commercialisti` · `idraulici` · `elettricisti` · `imprese-edili` · `agenzie-immobiliari` · `officine-meccaniche` · `hotel` · `palestre` · `scuole-guida` · `trasporti`

## Popular Locations (`where`)

Any Italian city or province: `roma` · `milano` · `napoli` · `torino` · `bologna` · `firenze` · `palermo` · `genova` · `venezia` · `bari`

## Pricing

**~$3.00 per 1,000 results** — significantly cheaper than alternatives on the Apify Store.

## Proxy

Residential Italian proxies (`proxyCountry: "IT"`) are strongly recommended for reliable results. The actor integrates directly with Apify's proxy infrastructure.

## Legal Notice

This actor extracts only publicly available information from PagineGialle.it for legitimate business, research, and lead generation purposes. Users are responsible for complying with applicable data protection laws (GDPR) and PagineGialle's Terms of Service when using the extracted data.
