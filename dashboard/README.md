# Task 4 — XAI Dashboard

React + Vite front-end for the Quality Grading & XAI service. The admin-facing half of the case study's Task 4 (Explainable AI & Admin Dashboard) — the Grad-CAM generation itself lives in [`../task2_3_4_quality_xai/`](../task2_3_4_quality_xai/README.md).

**Port:** 5173

## What's on the page

- **Navbar** — "DESD Marketplace — Quality Analysis"
- **Model Accuracy Chart** — rolling 7-day accuracy (Recharts line chart)
- **Recent Quality Assessments** — table of recent predictions: time, product, producer, grade, sub-scores, confidence
- **Image Upload** — file picker + live preview + "Analyze Quality" button, POSTs to `/explain`
- **Results** — classification, confidence, grade, plain-English explanation of which region drove the decision, and the Grad-CAM heatmap rendered inline from a base64 PNG

## API it talks to

Default: `http://localhost:8001/explain`. Override via `VITE_API_URL` at build time.

## Running

Via docker-compose (from repo root):

```bash
docker compose up xai-dashboard --build
```

Source is volume-mounted, so edits hot-reload through Vite.

Standalone (Node 20+):

```bash
npm install
npm run dev
```

The quality service needs to be running at `http://localhost:8001`.

## Build

```bash
npm run build    # production bundle → dist/
npm run preview  # serve the bundle locally
```

## Tech

React 19, Vite 8, Axios, Recharts, Bootstrap 5 + custom dark-theme CSS.

## Layout

```
dashboard/
├── src/
│   ├── App.jsx       # Upload, results, charts, recent assessments table
│   ├── main.jsx      # Entry point
│   ├── style.css     # Dark theme
│   ├── App.css
│   └── index.css
├── public/
├── vite.config.js
├── eslint.config.js
└── package.json
```
