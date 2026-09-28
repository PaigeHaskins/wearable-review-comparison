"""
Pull 2026 app reviews for Whoop and Oura from the App Store (and Google Play).

Run locally:
    pip install requests pandas google-play-scraper
    python fetch_reviews.py

Outputs (in data/raw/):
    app_store_reviews_raw.csv
    google_play_reviews_raw.csv
    reviews_combined_raw.csv

Reviewer names are intentionally NOT collected (privacy + safe for a public repo).
"""
import time
from pathlib import Path

import pandas as pd
import requests

# ---------------- Config ----------------
APP_SEARCH_TERMS = {"Whoop": "whoop", "Oura": "oura ring"}
PLAY_PACKAGES = {"Whoop": "com.whoop.android", "Oura": "com.ouraring.oura"}
COUNTRIES = ["us", "gb", "ca", "au"]  # Apple's feed caps at ~500 reviews per country
START_DATE = pd.Timestamp("2026-01-01", tz="UTC")
OUT_DIR = Path("data/raw")
PAUSE_SECONDS = 1  # be polite to the servers


# ---------------- App Store ----------------
def lookup_app_id(term):
    """Find the App Store ID via the public iTunes Search API."""
    r = requests.get(
        "https://itunes.apple.com/search",
        params={"term": term, "entity": "software", "country": "us", "limit": 5},
        timeout=20,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise ValueError(f"No App Store match for '{term}'")
    top = results[0]
    print(f"  Matched '{term}' -> {top['trackName']} (id {top['trackId']})  <- verify this is right")
    return top["trackId"]


def fetch_app_store(brand, app_id):
    rows = []
    for country in COUNTRIES:
        for page in range(1, 11):  # feed max = 10 pages x 50 reviews
            url = (
                f"https://itunes.apple.com/{country}/rss/customerreviews/"
                f"page={page}/id={app_id}/sortby=mostrecent/json"
            )
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                entries = r.json().get("feed", {}).get("entry", [])
            except (requests.RequestException, ValueError) as e:
                print(f"    {brand} {country} page {page}: stopped ({e})")
                break

            if isinstance(entries, dict):
                entries = [entries]
            reviews = [e for e in entries if "im:rating" in e]  # skip app-info entry
            if not reviews:
                break

            for e in reviews:
                rows.append({
                    "brand": brand,
                    "source": "app_store",
                    "country": country,
                    "review_id": e["id"]["label"],
                    "date": e["updated"]["label"],
                    "rating": int(e["im:rating"]["label"]),
                    "title": e["title"]["label"],
                    "text": e["content"]["label"],
                    "app_version": e.get("im:version", {}).get("label"),
                })

            oldest = pd.to_datetime(reviews[-1]["updated"]["label"], utc=True)
            if oldest < START_DATE:
                break  # past January 2026, move to next country
            time.sleep(PAUSE_SECONDS)
        print(f"    {brand} {country}: {sum(r['country'] == country for r in rows)} reviews")
    return rows


# ---------------- Google Play ----------------
def fetch_google_play(brand, package):
    from google_play_scraper import Sort, reviews

    rows, token = [], None
    while True:
        batch, token = reviews(
            package, lang="en", country="us", sort=Sort.NEWEST,
            count=200, continuation_token=token,
        )
        if not batch:
            break
        for b in batch:
            rows.append({
                "brand": brand,
                "source": "google_play",
                "country": "us",
                "review_id": b["reviewId"],
                "date": pd.Timestamp(b["at"], tz="UTC").isoformat(),
                "rating": b["score"],
                "title": None,
                "text": b["content"],
                "app_version": b.get("reviewCreatedVersion"),
            })
        if pd.Timestamp(batch[-1]["at"], tz="UTC") < START_DATE or token is None:
            break
        time.sleep(PAUSE_SECONDS)
    print(f"    {brand} google_play: {len(rows)} reviews")
    return rows


# ---------------- Main ----------------
def clean(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df[df["date"] >= START_DATE]
    df = df.drop_duplicates(subset=["source", "review_id"])
    return df.sort_values(["brand", "date"], ascending=[True, False])


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("App Store:")
    apple_rows = []
    for brand, term in APP_SEARCH_TERMS.items():
        apple_rows += fetch_app_store(brand, lookup_app_id(term))
    apple = clean(apple_rows)
    apple.to_csv(OUT_DIR / "app_store_reviews_raw.csv", index=False)

    print("Google Play:")
    play_rows = []
    for brand, package in PLAY_PACKAGES.items():
        try:
            play_rows += fetch_google_play(brand, package)
        except Exception as e:  # keep going if Play fails
            print(f"    {brand} google_play failed: {e}")
    play = clean(play_rows)
    play.to_csv(OUT_DIR / "google_play_reviews_raw.csv", index=False)

    combined = pd.concat([apple, play], ignore_index=True)
    combined.to_csv(OUT_DIR / "reviews_combined_raw.csv", index=False)

    print("\nReviews since Jan 1, 2026:")
    print(combined.groupby(["brand", "source"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
