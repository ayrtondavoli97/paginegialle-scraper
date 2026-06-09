# PagineGialle.it — Italian Yellow Pages Business Scraper

Extract structured business data from **PagineGialle.it** — Italy's #1 business directory.

## What you get

| Field | Description |
|---|---|
| `name` | Business name |
| `category` | Business category |
| `phone` | Phone number |
| `address` | Full address |
| `city` | City |
| `rating` | Customer rating |
| `sourceUrl` | PagineGialle profile URL |
| `searchWhat` | Search category |
| `searchWhere` | Search location |

## Input example

```json
{
  "searches": [
    { "what": "dentisti", "where": "roma" },
    { "what": "avvocati", "where": "milano" }
  ],
  "maxResults": 500,
  "useApifyProxy": true,
  "proxyCountry": "IT"
}
```

## Pricing

~$3.00 per 1,000 results.

## Legal

Extracts only publicly available data from PagineGialle.it.
Users are responsible for GDPR compliance when using extracted data.
