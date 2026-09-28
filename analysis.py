"""
Shared analysis logic for the Whoop vs Oura review project.

Used by both the Streamlit dashboard (app.py) and scripts/run_analysis.py,
so the numbers in the dashboard and the exported outputs always match.

Method notes
- Topics are tagged with transparent keyword rules (one review can have several topics).
  They are directional, not a trained classifier.
- Driver impact comes from a linear regression of star rating on topic flags:
  the coefficient is the average change in stars when a review mentions the topic,
  holding the other topics constant.
- Churn intent flags reviews that mention canceling, refunds, returns, or switching.
  It is a leading indicator of retention risk, not observed churn.
"""
import re

import numpy as np
import pandas as pd

# ---------------- Taxonomy ----------------
TOPICS = {
    "Subscription & price": r"subscri|membership|\bprice|pricing|expensive|\bcost|\bpay(ing|ment)?\b|\bmoney\b|\bfee\b|overcharg|charged (me|my)|auto.?renew",
    "App bugs & updates": r"\bbug|crash|glitch|freez|\bupdate|won'?t load|not loading|\blag|log ?in|sign ?in|\berror",
    "Sync & connectivity": r"\bsync|connect|bluetooth|\bpair|disconnect|apple health|health connect|google fit",
    "Battery & charging": r"batter|recharg|charger|charging|\bcharge (it|the|every|lasts)|battery pack",
    "Accuracy": r"accura|inaccura|\bwrong\b|incorrect|not track|doesn'?t track|didn'?t track|miss(ed|es|ing) (my|a|the)|false|reliab",
    "Hardware & comfort": r"\bband\b|strap|clasp|comfort|\brash|irritat|\bskin\b|\bsize|sizing|\bfit\b|broke|crack|scratch|hardware|\bsensor",
    "Customer service": r"customer service|customer support|\bsupport\b|warranty|replacement|\bagent\b|no response|never (heard|responded)|\bticket",
    "Sleep tracking": r"\bsleep|\bnap\b|bedtime|\brem\b|deep sleep",
    "Strain, recovery & HRV": r"\bstrain|recover|\bhrv\b|readiness|heart rate variability",
    "Insights & coaching": r"insight|\bcoach|motivat|\bhabit|journal|\badvice|recommendation|\bai\b|personaliz|understand my",
}

CHURN_PATTERN = (
    r"cancel|unsubscrib|refund|return(ed|ing)? (it|the|my|this)|sen(t|d) (it|the band|the ring) back|"
    r"switch(ed|ing)? (to|over)|going back to|moving to|move to|replac(ed|ing) (it|my \w+) with|"
    r"sell(ing)? (it|my)|get rid of|not renew|won'?t (be )?renew|stop(ped)? using|done with|"
    r"waste of money|no longer (use|wear)|bought an? (oura|garmin|apple watch|fitbit|galaxy)"
)

COMPETITORS = {
    "Oura": r"\boura",
    "Whoop": r"\bwhoop",
    "Apple Watch": r"apple watch|\biwatch",
    "Garmin": r"garmin",
    "Fitbit": r"fitbit",
    "Samsung": r"samsung|galaxy (watch|ring)",
    "Ultrahuman": r"ultrahuman",
}

# Recommended plays per topic, written for a Whoop stakeholder.
ACTIONS = {
    "Subscription & price": "Make the membership's value visible: monthly 'what your data did for you' recaps, clear plan comparisons, and a save offer or pause option in the cancel flow.",
    "App bugs & updates": "Add a release-quality gate: staged rollouts, crash-rate alerts, and a fast hotfix path for versions whose ratings dip after launch.",
    "Sync & connectivity": "Prioritize sync reliability with Apple Health and Health Connect, and show sync status clearly in the app.",
    "Battery & charging": "Improve battery messaging and low-battery nudges so tracking gaps don't happen overnight.",
    "Accuracy": "Explain how metrics are measured, and let members flag suspected tracking errors in the app to close the loop.",
    "Hardware & comfort": "Offer proactive band and fit guidance at onboarding and a fast replacement path for skin irritation or broken hardware.",
    "Customer service": "Set and publish a support response-time target, and route reviews that mention support to a recovery team.",
    "Sleep tracking": "Tighten sleep-stage accuracy and explain differences versus other devices.",
    "Strain, recovery & HRV": "Keep investing in the core strain and recovery experience; it is a differentiator.",
    "Insights & coaching": "Keep coaching and insights front and center in marketing and onboarding; it is what happy members praise most.",
}

LOW_CONFIDENCE_N = 20


# ---------------- Tagging ----------------
def _flag(text, pattern):
    """Case-insensitive regex match; groups are made non-capturing to keep pandas quiet."""
    pattern = re.sub(r"\((?!\?)", "(?:", pattern)
    return text.str.contains(pattern, regex=True)


def tag_reviews(df):
    """Add topic, churn-intent, and competitor-mention flags."""
    df = df.copy()
    text = df["text_clean"].fillna("").str.lower()
    for topic, pattern in TOPICS.items():
        df[topic] = _flag(text, pattern)
    df["churn_intent"] = _flag(text, CHURN_PATTERN)
    for name, pattern in COMPETITORS.items():
        df[f"mentions_{name}"] = _flag(text, pattern)
    df["topic_count"] = df[list(TOPICS)].sum(axis=1)
    return df


def mentioned_competitors(row, own_brand):
    return [c for c in COMPETITORS if c != own_brand and row.get(f"mentions_{c}", False)]


# ---------------- KPIs ----------------
def kpi_table(df):
    """One row per brand with the headline KPIs."""
    df = df[df["use_for_ratings"]]
    rows = []
    for brand, d in df.groupby("brand"):
        n = len(d)
        pct_pos = (d["rating"] >= 4).mean() * 100
        pct_neg = (d["rating"] <= 2).mean() * 100
        rows.append({
            "brand": brand,
            "reviews": n,
            "avg_rating": d["rating"].mean(),
            "pct_positive": pct_pos,
            "pct_negative": pct_neg,
            # Net Rating Score: % 5-star minus % 1-2 star (an NPS-style proxy, -100 to 100)
            "net_rating_score": (d["rating"] == 5).mean() * 100 - pct_neg,
            "churn_intent_rate": d["churn_intent"].mean() * 100,
        })
    return pd.DataFrame(rows).set_index("brand")


def monthly_trends(df):
    df = df[df["use_for_ratings"]]
    out = df.groupby(["brand", "month"]).agg(
        reviews=("rating", "size"),
        avg_rating=("rating", "mean"),
        pct_negative=("rating", lambda s: (s <= 2).mean() * 100),
        net_rating_score=("rating", lambda s: ((s == 5).mean() - (s <= 2).mean()) * 100),
        churn_intent_rate=("churn_intent", lambda s: s.mean() * 100),
    )
    return out.reset_index()


# ---------------- Topics & drivers ----------------
def topic_summary(df):
    """Mention rates by brand, overall and within negative / positive reviews."""
    df = df[df["use_for_topics"]]
    rows = []
    for brand, d in df.groupby("brand"):
        neg, pos = d[d["rating"] <= 2], d[d["rating"] >= 4]
        for topic in TOPICS:
            m = d[d[topic]]
            rows.append({
                "brand": brand,
                "topic": topic,
                "mentions": int(d[topic].sum()),
                "mention_rate": d[topic].mean() * 100,
                "share_of_negative": neg[topic].mean() * 100 if len(neg) else np.nan,
                "share_of_positive": pos[topic].mean() * 100 if len(pos) else np.nan,
                "avg_rating_when_mentioned": m["rating"].mean() if len(m) else np.nan,
                "churn_rate_when_mentioned": m["churn_intent"].mean() * 100 if len(m) else np.nan,
            })
    return pd.DataFrame(rows)


def driver_analysis(df, brand):
    """Regression of rating on topic flags for one brand.

    impact     = change in stars when the topic is mentioned (other topics held constant)
    priority   = mention rate x negative impact, i.e. total stars lost across the review base
    """
    d = df[(df["brand"] == brand) & df["use_for_topics"]]
    if len(d) < 30:
        return pd.DataFrame()
    X = d[list(TOPICS)].astype(float).to_numpy()
    X = np.column_stack([np.ones(len(X)), X])
    y = d["rating"].astype(float).to_numpy()
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)

    out = pd.DataFrame({
        "topic": list(TOPICS),
        "impact_stars": coefs[1:],
        "mentions": d[list(TOPICS)].sum().to_numpy(),
        "mention_rate": d[list(TOPICS)].mean().to_numpy() * 100,
    })
    out["stars_lost_per_100_reviews"] = np.where(
        out["impact_stars"] < 0, -out["impact_stars"] * out["mention_rate"], 0.0
    )
    out["confidence"] = np.where(out["mentions"] >= LOW_CONFIDENCE_N, "ok", "low (few mentions)")
    return out.sort_values("stars_lost_per_100_reviews", ascending=False).reset_index(drop=True)


# ---------------- Retention risk ----------------
def churn_by_topic(df, brand):
    d = df[(df["brand"] == brand) & df["use_for_topics"]]
    churn = d[d["churn_intent"]]
    if churn.empty:
        return pd.DataFrame(columns=["topic", "share_of_churn_reviews", "lift_vs_all_reviews"])
    rows = []
    for topic in TOPICS:
        share = churn[topic].mean() * 100
        base = d[topic].mean() * 100
        rows.append({
            "topic": topic,
            "share_of_churn_reviews": share,
            "lift_vs_all_reviews": share / base if base else np.nan,
        })
    return pd.DataFrame(rows).sort_values("share_of_churn_reviews", ascending=False)


def competitor_mentions(df, brand):
    d = df[df["brand"] == brand]
    rows = []
    for comp in COMPETITORS:
        if comp == brand:
            continue
        m = d[d[f"mentions_{comp}"]]
        rows.append({
            "competitor": comp,
            "mentions": len(m),
            "avg_rating_when_mentioned": m["rating"].mean() if len(m) else np.nan,
            "churn_intent_rate": m["churn_intent"].mean() * 100 if len(m) else np.nan,
        })
    return pd.DataFrame(rows).sort_values("mentions", ascending=False)


# ---------------- Releases ----------------
def version_sort_key(v):
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", str(v)))


def release_impact(df, brand, min_reviews=10):
    d = df[(df["brand"] == brand) & (df["app_version"] != "unknown") & df["use_for_ratings"]]
    out = d.groupby("app_version").agg(
        reviews=("rating", "size"),
        first_review=("date", "min"),
        avg_rating=("rating", "mean"),
        pct_negative=("rating", lambda s: (s <= 2).mean() * 100),
        bug_mention_rate=("App bugs & updates", lambda s: s.mean() * 100),
    ).reset_index()
    out = out[out["reviews"] >= min_reviews]
    out["first_review"] = out["first_review"].dt.date
    out = out.iloc[sorted(range(len(out)), key=lambda i: version_sort_key(out["app_version"].iloc[i]))]
    brand_avg = d["rating"].mean()
    out["vs_brand_avg"] = out["avg_rating"] - brand_avg
    return out.reset_index(drop=True)


# ---------------- Recommendations ----------------
def recommendations(df, brand, competitor):
    """Data-driven recommendations for `brand`, refreshed whenever the data changes."""
    recs = []
    drivers = driver_analysis(df, brand)
    topics = topic_summary(df)
    if drivers.empty:
        return recs

    own = topics[topics["brand"] == brand].set_index("topic")
    comp = topics[topics["brand"] == competitor].set_index("topic") if competitor else None

    # 1. Fix the biggest rating drags
    for _, r in drivers[(drivers["stars_lost_per_100_reviews"] > 0) & (drivers["confidence"] == "ok")].head(3).iterrows():
        t = r["topic"]
        neg_share = own.loc[t, "share_of_negative"]
        recs.append({
            "type": "Fix",
            "topic": t,
            "evidence": (f"Mentioned in {neg_share:.0f}% of negative reviews; a mention lowers the rating by "
                         f"{abs(r['impact_stars']):.2f} stars on average."),
            "action": ACTIONS[t],
            "kpi": f"Cut the share of negative reviews mentioning {t.lower()} from {neg_share:.0f}% to {neg_share * 0.75:.0f}%.",
        })

    # 2. Double down on the biggest strength
    pos = drivers[(drivers["impact_stars"] > 0) & (drivers["confidence"] == "ok")].sort_values("impact_stars", ascending=False)
    if not pos.empty:
        t = pos.iloc[0]["topic"]
        recs.append({
            "type": "Amplify",
            "topic": t,
            "evidence": (f"Mentioned in {own.loc[t, 'share_of_positive']:.0f}% of positive reviews; a mention raises the rating by "
                         f"{pos.iloc[0]['impact_stars']:.2f} stars on average."),
            "action": ACTIONS[t],
            "kpi": f"Grow the share of positive reviews mentioning {t.lower()}.",
        })

    # 3. Win switchers: where the competitor struggles more
    if comp is not None and not comp.empty:
        gap = (comp["share_of_negative"] - own["share_of_negative"]).dropna().sort_values(ascending=False)
        if not gap.empty and gap.iloc[0] > 5:
            t = gap.index[0]
            recs.append({
                "type": "Win switchers",
                "topic": t,
                "evidence": (f"{competitor} reviewers complain about {t.lower()} far more often "
                             f"({comp.loc[t, 'share_of_negative']:.0f}% vs {own.loc[t, 'share_of_negative']:.0f}% of negative reviews)."),
                "action": f"Use {t.lower()} as a proof point in comparison marketing and switcher offers aimed at {competitor} users.",
                "kpi": f"Track reviews mentioning {competitor} and the rating among them.",
            })
    return recs
