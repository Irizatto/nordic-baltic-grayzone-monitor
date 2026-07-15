# Project rules

- Describe outputs only as a **risk signal**, **anomaly**, **review priority**, or **lead for human review**. Never claim a vessel is hostile, guilty, a confirmed saboteur, or attributable to a state.
- Never put API tokens or secrets in code. Credentials may come only from environment variables or GitHub Secrets.
- When a source or credential is unavailable, gracefully use mock data and keep the frontend functional. Record fallbacks in `docs/data/metadata.json`.
- Never delete or overwrite existing data files; write new, dated outputs when preserving source data matters.
- The frontend is vanilla HTML, CSS, and JavaScript using Leaflet.js and Chart.js only: no React, Vue, or build tools. The pipeline is Python 3.11+ using pandas, geopandas, shapely, requests, and python-dotenv.
- GitHub Pages serves the `docs/` folder.
- All user-facing text is bilingual English and Simplified Chinese where practical, with English primary.
- At the end of every task report files changed, why, how to run/check, what remains mock, and the recommended next step.

