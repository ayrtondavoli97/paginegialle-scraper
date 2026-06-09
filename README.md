# PagineGialle.it — Italian Yellow Pages Business Scraper

Extract structured business data from **PagineGialle.it** — Italy's #1 online business directory with 3+ million monthly visitors. Perfect for B2B lead generation, local SEO research, and sales prospecting across Italy.

## 🚀 What you get

| Field | Description |
|---|---|
| `name` | Business name |
| `category` | Business category (e.g. Restaurant, Dentist, Lawyer) |
| `phone` | Phone number |
| `email` | Email address (when publicly listed) |
| `website` | Website URL |
| `address` | Full street address |
| `city` | City |
| `province` | Province / Region |
| `postalCode` | ZIP / Postal code |
| `latitude` | GPS latitude |
| `longitude` | GPS longitude |
| `rating` | Customer rating (0–5 stars) |
| `reviewCount` | Number of customer reviews |
| `profileUrl` | PagineGialle.it business profile URL |
| `searchCategory` | The category that was searched |
| `searchCity` | The city that was searched |

## 🎯 Use cases

- **B2B Lead Generation** — build targeted prospect lists by industry and city
- **Sales Prospecting** — extract phones and addresses for outreach campaigns
- **Market Research** — analyze business density and competition by area
- **CRM Enrichment** — enrich existing records with contact data
- **Local SEO Analysis** — map business profiles across Italian cities

## ⚙️ How to use

1. **Select categories** from the dropdown (Restaurant, Dentist, Plumber, Hotel...)
2. **Select cities** from the dropdown (Rome, Milan, Naples, Florence...)
3. Set **Max Results per Search** (200 recommended, up to 5000 for large cities)
4. Click **Start** — results appear in the dataset within minutes

> **Tip**: 3 categories × 5 cities = 15 searches generated automatically.

## 📋 Input example

Using the **Advanced: Raw Search Queries** field for custom combinations:

```json
[
  { "what": "ristorante", "where": "roma" },
  { "what": "dentista",   "where": "milano" },
  { "what": "avvocato",   "where": "napoli" }
]
```

Custom categories not in the dropdown (use the **Custom Categories** text field):
```
tatuaggi
erboristeria
pompe-funebri
```

## 🏙️ Available categories (40+)

| Category | Italian term |
|---|---|
| Restaurant | ristorante |
| Pizzeria | pizzeria |
| Bar / Café | bar |
| Dentist | dentista |
| Doctor / GP | medico |
| Pharmacy | farmacia |
| Hair Salon | parrucchiere |
| Lawyer | avvocato |
| Accountant | commercialista |
| Real Estate Agency | agenzia-immobiliare |
| Plumber | idraulico |
| Electrician | elettricista |
| Auto Repair Shop | officina-meccanica |
| Hotel | hotel |
| Bed & Breakfast | bed-and-breakfast |
| Gym | palestra |
| Driving School | scuola-guida |
| Bakery | panificio |
| *+ 22 more...* | |

## 🏙️ Available cities (40+)

Rome, Milan, Naples, Turin, Bologna, Florence, Palermo, Genoa, Venice, Bari, Catania, Verona, Padua, Trieste, Brescia, and 25+ more.

For cities not in the dropdown, use the **Custom Cities** text field.

## 💰 Pricing

**~$3.00 per 1,000 results** — significantly cheaper than alternatives.

Typical costs:
- 200 dentists in Rome → ~$0.60
- 500 restaurants in Milan → ~$1.50
- 2,000 lawyers in Italy (10 cities) → ~$6.00

## ⚡ Performance

| City size | Districts | Results | Time |
|---|---|---|---|
| Large (Rome, Milan) | 73–144 | 500–2,500 | ~2–4 min |
| Medium (Bologna, Verona) | 20–40 | 100–600 | ~1–2 min |
| Small | 5–15 | 25–200 | ~30 sec |

## 📌 Notes

- Data is scraped from publicly available PagineGialle.it listings
- Phone numbers are always visible (no click-to-reveal needed)
- Email and website availability varies by listing (~10–30%)
- Ratings only shown for businesses with at least 1 review
- Results are deduplicated automatically

## ⚖️ Legal

This actor extracts only publicly available information from PagineGialle.it for legitimate business, research, and lead generation purposes. Users are responsible for complying with applicable data protection regulations (GDPR) when storing and using the extracted data.
