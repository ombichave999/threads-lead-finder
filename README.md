# 24/7 Threads Website Client Lead Finder

Automated 24/7 cloud workflow that monitors Threads for prospective clients looking to hire website designers, developers, and freelancers.

## Architecture
- **Runner:** GitHub Actions runs `scraper.py` on a recurring schedule (`*/30 * * * *`).
- **Storage:** Persists discovered leads directly into `leads.csv` in this repository.
- **Deduplication:** Prevents duplicate post URLs across runs.
- **Sync:** Automatically pushes updates to Google Sheets via `GOOGLE_SHEET_WEBHOOK` secret.

## Live Dashboard
Telemetry and lead dashboard deployed at: [dashboard-ebon-tau-19.vercel.app](https://dashboard-ebon-tau-19.vercel.app)
