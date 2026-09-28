"""
Whoop vs Oura customer voice dashboard.

Run locally:   streamlit run app.py
Deploy:        Streamlit Community Cloud -> point it at this repo, main file app.py
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an

# ---------------- Design tokens ----------------
# Sentiment colors borrow the recovery-zone language wearable users already know.
GREEN, AMBER, RED = "#2E9E6B", "#E0A526", "#D14B4B"
INK, MUTED, GRID = "#1C2321", "#5B6663", "#E3E7E5"
BRAND_COLORS = {"Whoop": "#2F5D8A", "Oura": "#A07D4A"}

DATA_DIR = Path(__file__).parent / "data" / "clean"
SOURCES = {
    "Google Play (Jan–Sep 2026)": "google_play",
    "App Store, US (recent window)": "app_store",
}

st.set_page_config(page_title="Wearable customer voice", page_icon="⌚", layout="wide")

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
    html, body, [class*="css"], .stMarkdown, .stMetric {{ font-family: 'IBM Plex Sans', system-ui, sans-serif; }}
    h1 {{ font-weight: 600; letter-spacing: -0.02em; color: {INK}; }}
    h2, h3 {{ font-weight: 600; color: {INK}; }}
    [data-testid="stMetricValue"] {{ font-weight: 500; }}
    .subtle {{ color: {MUTED}; font-size: 0.95rem; max-width: 72ch; }}
    .rec-type {{ font-weight: 600; font-size: 0.85rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def style_fig(fig, height=360):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", color=INK),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


# ---------------- Data ----------------
@st.cache_data
def load_data():
    frames = []
    for name in ["google_play_clean.csv", "app_store_recent_clean.csv"]:
        path = DATA_DIR / name
        if path.exists():
            frames.append(pd.read_csv(path, dtype={"review_id": str}))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["app_version"] = df["app_version"].fillna("unknown").astype(str)
    df["text_clean"] = df["text_clean"].fillna("")
    return an.tag_reviews(df)


data = load_data()
if data.empty:
    st.error("No data found. Add the cleaned CSVs to data/clean/ (run scripts/clean_reviews.py), then reload.")
    st.stop()

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Filters")
    brands = sorted(data["brand"].unique())
    brand = st.selectbox("Your brand", brands, index=brands.index("Whoop") if "Whoop" in brands else 0)
    others = [b for b in brands if b != brand]
    competitor = st.selectbox("Compare with", others) if others else None

    source_label = st.radio("Review source", list(SOURCES))
    source = SOURCES[source_label]

    src = data[data["source"] == source]
    months = sorted(src["month"].unique())
    if len(months) > 1:
        start_m, end_m = st.select_slider("Months", options=months, value=(months[0], months[-1]))
    else:
        start_m = end_m = months[0]

    ratings = st.multiselect("Star ratings", [1, 2, 3, 4, 5], default=[1, 2, 3, 4, 5])

    st.caption(
        "App Store data covers a matched recent window only, because Apple's public feed "
        "returns the latest reviews. Use Google Play for trends over time."
    )

df = src[(src["month"] >= start_m) & (src["month"] <= end_m) & (src["rating"].isin(ratings))]
if df.empty or brand not in df["brand"].unique():
    st.info("No reviews match these filters. Widen the month range or add star ratings in the sidebar.")
    st.stop()

kpis = an.kpi_table(df)
own = kpis.loc[brand]
comp = kpis.loc[competitor] if competitor in kpis.index else None

# ---------------- Header ----------------
st.title(f"{brand} customer voice")
st.markdown(
    f"<p class='subtle'>{int(own['reviews']):,} {brand} reviews and "
    f"{int(comp['reviews']) if comp is not None else 0:,} {competitor or ''} reviews from {source_label.split(' (')[0]}, "
    f"{start_m} to {end_m}. Built to show what drives satisfaction and retention risk, and what to do about it.</p>",
    unsafe_allow_html=True,
)

# Hero: Net Rating Score gauge in recovery-zone bands
hero_left, hero_right = st.columns([1.1, 2])
with hero_left:
    gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=own["net_rating_score"],
        number=dict(suffix="", font=dict(size=48)),
        delta=dict(reference=comp["net_rating_score"], position="bottom",
                   increasing=dict(color=GREEN), decreasing=dict(color=RED)) if comp is not None else None,
        gauge=dict(
            axis=dict(range=[-100, 100], tickvals=[-100, -50, 0, 50, 100]),
            bar=dict(color=INK, thickness=0.25),
            steps=[dict(range=[-100, 0], color="#F4D3D3"),
                   dict(range=[0, 30], color="#F7E6BD"),
                   dict(range=[30, 100], color="#CDEBDD")],
        ),
        title=dict(text=f"Net Rating Score<br><span style='font-size:0.8em;color:{MUTED}'>"
                        f"% 5-star minus % 1–2 star, vs {competitor}</span>"),
    ))
    st.plotly_chart(style_fig(gauge, height=300), use_container_width=True)

with hero_right:
    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    delta = lambda col, fmt: (fmt.format(own[col] - comp[col]) + f" vs {competitor}") if comp is not None else None
    c1.metric("Average rating", f"{own['avg_rating']:.2f} ★", delta("avg_rating", "{:+.2f}"))
    c2.metric("Negative reviews (1–2★)", f"{own['pct_negative']:.1f}%", delta("pct_negative", "{:+.1f} pts"),
              delta_color="inverse")
    c3.metric("Churn-intent rate", f"{own['churn_intent_rate']:.1f}%", delta("churn_intent_rate", "{:+.1f} pts"),
              delta_color="inverse", help="Share of reviews mentioning canceling, refunds, returns, or switching brands.")
    c4.metric("Positive reviews (4–5★)", f"{own['pct_positive']:.1f}%", delta("pct_positive", "{:+.1f} pts"))

tab_overview, tab_drivers, tab_risk, tab_releases, tab_recs, tab_method = st.tabs(
    ["Trends", "What drives ratings", "Retention risk", "App releases", "Recommendations", "Data & method"]
)

# ---------------- Trends ----------------
with tab_overview:
    trends = an.monthly_trends(df)
    metric_labels = {
        "Average rating": "avg_rating",
        "Negative reviews (%)": "pct_negative",
        "Net Rating Score": "net_rating_score",
        "Churn-intent rate (%)": "churn_intent_rate",
        "Review volume": "reviews",
    }
    choice = st.radio("Metric", list(metric_labels), horizontal=True)
    fig = px.line(trends, x="month", y=metric_labels[choice], color="brand", markers=True,
                  color_discrete_map=BRAND_COLORS, labels={"month": "", metric_labels[choice]: choice})
    st.plotly_chart(style_fig(fig), use_container_width=True)
    if source == "app_store":
        st.caption("The App Store window is short, so treat monthly movement here as a snapshot, not a trend.")

    st.subheader("Rating distribution")
    dist = (df.groupby(["brand", "rating"]).size() / df.groupby("brand").size()).mul(100).rename("pct").reset_index()
    fig = px.bar(dist, x="rating", y="pct", color="brand", barmode="group", color_discrete_map=BRAND_COLORS,
                 labels={"rating": "Stars", "pct": "% of reviews"})
    st.plotly_chart(style_fig(fig, 300), use_container_width=True)
    st.caption("Both brands are polarized: most reviewers either love the product or are frustrated enough to leave 1 star.")

# ---------------- Drivers ----------------
with tab_drivers:
    drivers = an.driver_analysis(df, brand)
    if drivers.empty:
        st.info("Not enough reviews in this selection to estimate drivers. Widen the filters.")
    else:
        st.subheader(f"What moves {brand}'s star rating")
        st.markdown(
            "<p class='subtle'>Each bar is the average change in stars when a review mentions the topic, "
            "holding other topics constant. Red topics pull ratings down; green topics lift them.</p>",
            unsafe_allow_html=True,
        )
        plot = drivers.sort_values("impact_stars")
        fig = go.Figure(go.Bar(
            x=plot["impact_stars"], y=plot["topic"], orientation="h",
            marker_color=[RED if v < 0 else GREEN for v in plot["impact_stars"]],
            customdata=plot[["mentions", "confidence"]],
            hovertemplate="%{y}<br>%{x:+.2f} stars<br>%{customdata[0]} mentions (%{customdata[1]})<extra></extra>",
        ))
        fig.update_xaxes(title="Change in stars when mentioned")
        st.plotly_chart(style_fig(fig, 420), use_container_width=True)

        st.subheader("Where the stars are lost")
        lost = drivers[drivers["stars_lost_per_100_reviews"] > 0][
            ["topic", "mention_rate", "impact_stars", "stars_lost_per_100_reviews", "confidence"]]
        st.dataframe(
            lost.rename(columns={"topic": "Topic", "mention_rate": "Mentioned in (%)", "impact_stars": "Stars per mention",
                                 "stars_lost_per_100_reviews": "Stars lost per 100 reviews", "confidence": "Confidence"}),
            hide_index=True, use_container_width=True,
            column_config={"Mentioned in (%)": st.column_config.NumberColumn(format="%.1f"),
                           "Stars per mention": st.column_config.NumberColumn(format="%.2f"),
                           "Stars lost per 100 reviews": st.column_config.NumberColumn(format="%.1f")},
        )
        st.caption("Stars lost per 100 reviews combines how often a topic comes up with how much it hurts, so it ranks what to fix first.")

    st.subheader(f"{brand} vs {competitor}: complaint topics")
    topics = an.topic_summary(df)
    heat = topics.pivot(index="topic", columns="brand", values="share_of_negative").round(0)
    fig = px.imshow(heat, text_auto=True, aspect="auto",
                    color_continuous_scale=["#FFFFFF", "#F4D3D3", RED],
                    labels=dict(color="% of negative reviews"))
    fig.update_xaxes(title=None, side="top")
    fig.update_yaxes(title=None)
    st.plotly_chart(style_fig(fig, 440), use_container_width=True)

    st.subheader("Read the reviews")
    q1, q2 = st.columns([2, 1])
    topic_pick = q1.selectbox("Topic", list(an.TOPICS))
    tone = q2.radio("Tone", ["Negative", "Positive"], horizontal=True)
    quotes = df[(df["brand"] == brand) & df[topic_pick] & df["use_for_topics"]]
    quotes = quotes[quotes["rating"] <= 2] if tone == "Negative" else quotes[quotes["rating"] >= 4]
    quotes = quotes.sort_values("date", ascending=False).head(15)
    if quotes.empty:
        st.info(f"No {tone.lower()} {brand} reviews mention {topic_pick.lower()} in this selection.")
    else:
        st.dataframe(
            quotes.assign(date=quotes["date"].dt.date)[["date", "rating", "text_clean"]]
            .rename(columns={"date": "Date", "rating": "Stars", "text_clean": "Review"}),
            hide_index=True, use_container_width=True,
        )

# ---------------- Retention risk ----------------
with tab_risk:
    st.subheader("Churn intent over time")
    st.markdown(
        "<p class='subtle'>Churn intent flags reviews that mention canceling, refunds, returns, or switching brands. "
        "It is a leading indicator of retention risk, not observed churn.</p>",
        unsafe_allow_html=True,
    )
    fig = px.line(an.monthly_trends(df), x="month", y="churn_intent_rate", color="brand", markers=True,
                  color_discrete_map=BRAND_COLORS, labels={"month": "", "churn_intent_rate": "% of reviews"})
    st.plotly_chart(style_fig(fig, 320), use_container_width=True)

    r1, r2 = st.columns(2)
    with r1:
        st.subheader("What churn-risk reviews talk about")
        cbt = an.churn_by_topic(df, brand)
        if cbt.empty:
            st.info("No churn-intent reviews in this selection.")
        else:
            fig = px.bar(cbt.sort_values("share_of_churn_reviews"), x="share_of_churn_reviews", y="topic",
                         orientation="h", color="lift_vs_all_reviews",
                         color_continuous_scale=["#F7E6BD", AMBER, RED],
                         labels={"share_of_churn_reviews": "% of churn-risk reviews", "topic": "",
                                 "lift_vs_all_reviews": "Lift vs all"})
            st.plotly_chart(style_fig(fig, 400), use_container_width=True)
            st.caption("Lift above 1 means the topic is over-represented among members at risk of leaving.")
    with r2:
        st.subheader("Other brands mentioned")
        cm = an.competitor_mentions(df, brand)
        st.dataframe(
            cm.rename(columns={"competitor": "Brand", "mentions": "Mentions",
                               "avg_rating_when_mentioned": "Avg rating", "churn_intent_rate": "Churn intent (%)"}),
            hide_index=True, use_container_width=True,
            column_config={"Avg rating": st.column_config.NumberColumn(format="%.2f"),
                           "Churn intent (%)": st.column_config.NumberColumn(format="%.0f")},
        )
        st.caption("Low counts; read these as qualitative signals about who members compare against.")

    st.subheader("Churn-risk reviews")
    risk = df[(df["brand"] == brand) & df["churn_intent"]].sort_values("date", ascending=False).head(15)
    if not risk.empty:
        st.dataframe(
            risk.assign(date=risk["date"].dt.date)[["date", "rating", "text_clean"]]
            .rename(columns={"date": "Date", "rating": "Stars", "text_clean": "Review"}),
            hide_index=True, use_container_width=True,
        )

# ---------------- Releases ----------------
with tab_releases:
    rel = an.release_impact(df, brand)
    if rel.empty:
        st.info("Not enough reviews per app version in this selection. Widen the filters.")
    else:
        st.subheader(f"{brand} rating by app version")
        st.markdown(
            f"<p class='subtle'>Versions with at least 10 reviews, compared with {brand}'s average. "
            "Red bars mark releases that underperformed and are worth a closer look.</p>",
            unsafe_allow_html=True,
        )
        fig = go.Figure(go.Bar(
            x=rel["app_version"], y=rel["vs_brand_avg"],
            marker_color=[RED if v < -0.25 else (GREEN if v > 0.25 else "#B8C2BE") for v in rel["vs_brand_avg"]],
            customdata=rel[["reviews", "avg_rating", "bug_mention_rate"]],
            hovertemplate=("Version %{x}<br>%{customdata[1]:.2f} ★ (%{y:+.2f} vs avg)"
                           "<br>%{customdata[0]} reviews<br>%{customdata[2]:.0f}% mention bugs<extra></extra>"),
        ))
        fig.update_xaxes(type="category", title="App version")
        fig.update_yaxes(title="Stars vs brand average")
        st.plotly_chart(style_fig(fig, 380), use_container_width=True)
        worst = rel.nsmallest(3, "vs_brand_avg")
        st.caption("Lowest-rated releases: " + ", ".join(
            f"{v} ({d:+.2f}★, {b:.0f}% mention bugs)" for v, d, b in
            zip(worst["app_version"], worst["vs_brand_avg"], worst["bug_mention_rate"])) + ".")

# ---------------- Recommendations ----------------
with tab_recs:
    st.subheader(f"Recommended actions for {brand}")
    st.markdown(
        "<p class='subtle'>Generated from the current filters, so they update as new reviews are added.</p>",
        unsafe_allow_html=True,
    )
    recs = an.recommendations(df, brand, competitor)
    if not recs:
        st.info("Not enough data in this selection to make recommendations. Widen the filters.")
    type_color = {"Fix": RED, "Amplify": GREEN, "Win switchers": BRAND_COLORS.get(brand, INK)}
    for rec in recs:
        with st.container(border=True):
            st.markdown(f"<span class='rec-type' style='color:{type_color[rec['type']]}'>{rec['type']}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"**{rec['topic']}**")
            st.markdown(rec["evidence"])
            st.markdown(f"**Action:** {rec['action']}")
            st.markdown(f"**Target:** {rec['kpi']}")

# ---------------- Method ----------------
with tab_method:
    st.subheader("Data")
    st.markdown(
        "- **Google Play (US):** January 1 to September 27, 2026. Primary source for trends.\n"
        "- **App Store (US):** matched recent window where both brands have reviews. Apple's public feed only returns recent reviews.\n"
        "- Reviewer names are not collected. Non-English reviews are excluded from ratings; "
        "reviews under 20 characters are excluded from topic analysis."
    )
    st.subheader("Method")
    st.markdown(
        "- **Topics** are tagged with transparent keyword rules, and a review can mention several topics. "
        "They are directional rather than a trained classifier.\n"
        "- **Driver impact** is a linear regression of star rating on topic flags.\n"
        "- **Net Rating Score** is % 5-star minus % 1–2 star, an NPS-style proxy from −100 to 100.\n"
        "- **Churn intent** flags mentions of canceling, refunds, returns, or switching. It indicates expressed risk, not actual churn.\n"
        "- Reviews reflect people motivated to write one, so they skew toward strong opinions."
    )
    with st.expander("Topic keyword rules"):
        st.dataframe(pd.DataFrame({"Topic": list(an.TOPICS), "Pattern": list(an.TOPICS.values())}),
                     hide_index=True, use_container_width=True)
