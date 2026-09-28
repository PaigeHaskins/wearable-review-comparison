"""
Clean the raw Whoop vs Oura review data.

Primary dataset:  Google Play (US), Jan 1 2026 onward -> trend analysis
Secondary dataset: App Store (US), recent window only  -> recent-period comparison

Run in Colab or locally:
    python clean_reviews.py

Input:   data/raw/reviews_combined_raw.csv
Outputs: data/clean/google_play_clean.csv
         data/clean/app_store_recent_clean.csv
"""
import re
from pathlib import Path

import pandas as pd

# ---------------- Config ----------------
RAW_FILE = Path("data/raw/reviews_combined_raw.csv")
OUT_DIR = Path("data/clean")
START_DATE = pd.Timestamp("2026-01-01", tz="UTC")
MIN_TOPIC_CHARS = 20            # shorter reviews are kept for ratings, excluded from topic work
NON_LATIN_THRESHOLD = 0.30      # share of non-Latin letters that flags a review as non-English
APP_STORE_COUNTRIES = ["us"]    # other countries have uneven coverage by brand


# ---------------- Helpers ----------------
def normalize_text(text):
    """Collapse whitespace and standardize curly quotes; keeps original wording."""
    text = str(text).replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip()


def language_flag(text):
    """Return 'english', 'non_english', or 'no_words' (emoji/symbols only)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "no_words"
    non_latin = sum(ord(c) > 0x24F for c in letters)
    return "non_english" if non_latin / len(letters) > NON_LATIN_THRESHOLD else "english"


def sentiment_bucket(rating):
    if rating <= 2:
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


# ---------------- Cleaning ----------------
def clean(df):
    df = df.copy()

    # Types
    df["review_id"] = df["review_id"].astype(str).str.strip()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["brand"] = df["brand"].str.strip().str.title()

    # Validity checks
    df = df[df["date"] >= START_DATE]
    df = df[df["rating"].between(1, 5)]
    df = df.drop_duplicates(subset=["source", "review_id"])
    df["rating"] = df["rating"].astype(int)

    # Text
    df["title"] = df["title"].fillna("")          # Google Play has no titles by design
    df["text_clean"] = df["text"].fillna("").map(normalize_text)
    df = df[df["text_clean"] != ""]
    df["app_version"] = df["app_version"].fillna("unknown")

    # Features
    df["char_count"] = df["text_clean"].str.len()
    df["word_count"] = df["text_clean"].str.split().str.len()
    df["language_flag"] = df["text_clean"].map(language_flag)
    df["sentiment_bucket"] = df["rating"].map(sentiment_bucket)
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["week_start"] = (df["date"].dt.tz_localize(None).dt.to_period("W-SUN")
                        .dt.start_time.dt.date)

    # Analysis-ready flags
    df["use_for_ratings"] = df["language_flag"] != "non_english"
    df["use_for_topics"] = (df["language_flag"] == "english") & (df["char_count"] >= MIN_TOPIC_CHARS)

    cols = ["brand", "source", "country", "review_id", "date", "month", "week_start",
            "rating", "sentiment_bucket", "title", "text", "text_clean", "app_version",
            "char_count", "word_count", "language_flag", "use_for_ratings", "use_for_topics"]
    return df[cols].sort_values(["brand", "date"], ascending=[True, False]).reset_index(drop=True)


def recent_window_start(app_store):
    """Latest start date across brands, so both brands cover the same window."""
    return app_store.groupby("brand")["date"].min().max().normalize()


def summarize(name, df):
    print(f"\n=== {name}: {len(df):,} reviews ===")
    print(f"Date range: {df['date'].min():%Y-%m-%d} to {df['date'].max():%Y-%m-%d}")
    summary = df.groupby("brand").agg(
        reviews=("review_id", "count"),
        avg_rating=("rating", "mean"),
        pct_negative=("sentiment_bucket", lambda s: (s == "negative").mean() * 100),
        rating_ready=("use_for_ratings", "sum"),
        topic_ready=("use_for_topics", "sum"),
    ).round(2)
    print(summary.to_string())


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(RAW_FILE, dtype={"review_id": str})
    print(f"Loaded {len(raw):,} raw reviews")

    cleaned = clean(raw)
    print(f"Removed {len(raw) - len(cleaned):,} invalid, duplicate, or empty rows")

    # Primary: Google Play
    google_play = cleaned[cleaned["source"] == "google_play"].copy()

    # Secondary: App Store, recent matched window
    app_store = cleaned[(cleaned["source"] == "app_store")
                        & (cleaned["country"].isin(APP_STORE_COUNTRIES))].copy()
    window_start = recent_window_start(app_store)
    app_store = app_store[app_store["date"] >= window_start]

    # Flag the same window in Google Play for apples-to-apples comparisons
    google_play["in_recent_window"] = google_play["date"] >= window_start

    google_play.to_csv(OUT_DIR / "google_play_clean.csv", index=False)
    app_store.to_csv(OUT_DIR / "app_store_recent_clean.csv", index=False)

    summarize("Google Play (primary)", google_play)
    summarize(f"App Store recent window (from {window_start:%Y-%m-%d})", app_store)
    print(f"\nSaved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
