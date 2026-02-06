# Frontend

The frontend lives in `frontend/brr-frontend` and is a Next.js app focused on
sentiment and reputation analysis.

## Key routes
- `/`: overview dashboard.
- `/sentimiento`: deep sentiment analysis view.

## Data sources
The UI reads from the API endpoints:
- `/reputation/meta` for profiles, sources, and cache state.
- `/reputation/items` for filtered mentions.
- `/ingest/*` for ingest status.

## Main components
- `src/components/Shell.tsx`: global layout, navigation, ingest status.
- `src/components/SentimentView.tsx`: charts, filters, and mention lists.

## Styling
The UI uses a branded theme with CSS variables in `src/app/globals.css` and
Google fonts configured in `src/app/layout.tsx`.
