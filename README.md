# Wearables Marketing Analytics: Whoop vs Oura

An interactive dashboard that turns public app reviews into KPIs and retention insights, written from the point of view of a Whoop stakeholder.

**Live dashboard:** _add your Streamlit link here_

## Business question
What drives customer satisfaction and retention risk for Whoop compared with Oura, and what should Whoop do about it?

## Key findings (Google Play, Jan 1 to Sep 27, 2026)
| KPI | Whoop | Oura |
|---|---|---|
| Reviews | 843 | 1,286 |
| Average rating | 3.44 | 3.27 |
| Net Rating Score (% 5-star minus % 1–2 star) | +12.8 | +1.2 |
| Negative reviews (1–2 stars) | 34.6% | 35.5% |
| Churn-intent rate | 4.2% | 3.6% |

- **Subscription and price is Whoop's biggest rating drag.** It is mentioned in about a third of negative reviews, lowers the rating by about 1.2 stars when mentioned, and appears in 69% of churn-risk reviews (3.8x its overall rate).
- **App bugs and customer service are the next two drags.** Customer service is also heavily over-represented among churn-risk reviews (3.6x).
- **Oura members complain about battery and sync far more than Whoop members**, which gives Whoop a clear proof point for winning switchers.
- Reviews reflect expressed sentiment, so churn intent is a leading indicator, not observed churn.

Full recommendations are in [`outputs/recommendations.md`](outputs/recommendations.md) and in the dashboard's Recommendations tab.

## Dashboard
- **Header:** Net Rating Score gauge and KPI cards compared with Oura
- **Trends:** monthly rating, negative share, Net Rating Score, churn intent, and volume
- **What drives ratings:** regression-based driver impact, complaint heatmap by brand, and a review reader by topic
- **Retention risk:** churn intent over time, topics behind churn risk, and competitor mentions
- **App releases:** rating by app version against the brand average
- **Recommendations:** fix, amplify, and win-switcher actions with targets, regenerated from the filtered data

## Data
| Source | Role | Coverage | Oura | Whoop |
|---|---|---|---|---|
| Google Play (US) | Primary: trends over time | Jan 1 to Sep 27, 2026 | 1,287 | 846 |
| App Store (US) | Secondary: recent-period comparison | Aug 9 to Sep 27, 2026 | 209 | 200 |

Apple's public review feed only returns recent reviews, so App Store data is limited to a matched recent window. Reviewer names are not collected.

## Method
- **Cleaning:** type validation, deduplication, text normalization, language flags, and analysis-ready flags (`scripts/clean_reviews.py`)
- **Topics:** transparent keyword rules for 10 topics; a review can mention several (`analysis.py`)
- **Drivers:** linear regression of star rating on topic flags; "stars lost per 100 reviews" ranks what to fix first
- **Churn intent:** mentions of canceling, refunds, returns, or switching brands

## Repo structure
```
app.py                  Streamlit dashboard
analysis.py             shared analysis logic (topics, KPIs, drivers, churn, recommendations)
scripts/
  fetch_reviews.py      pulls App Store and Google Play reviews
  clean_reviews.py      validates, cleans, and flags reviews
  run_analysis.py       exports analysis tables to outputs/
data/
  raw/                  reviews_combined_raw.csv
  clean/                google_play_clean.csv, app_store_recent_clean.csv
outputs/                KPI, driver, churn, release, and recommendation outputs
.streamlit/config.toml  dashboard theme
```

## Run it yourself
```
pip install -r requirements.txt
python scripts/fetch_reviews.py     # optional: refresh the data
python scripts/clean_reviews.py
python scripts/run_analysis.py
streamlit run app.py
```
Run all commands from the repo root.

## Next steps
- Add Apple Watch reviews
- Replace keyword topics with BERTopic and compare
- Add Google Trends share of voice
