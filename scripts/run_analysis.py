"""
Export the analysis tables behind the dashboard (Google Play, primary dataset).

Run from the repo root:
    python scripts/run_analysis.py

Outputs in outputs/:
    kpis.csv, monthly_trends.csv, topic_summary.csv, drivers_<brand>.csv,
    churn_by_topic_<brand>.csv, release_impact_<brand>.csv, recommendations.md
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analysis as an  # noqa: E402

FOCUS_BRAND, COMPETITOR = "Whoop", "Oura"
OUT = ROOT / "outputs"


def main():
    OUT.mkdir(exist_ok=True)
    df = pd.read_csv(ROOT / "data" / "clean" / "google_play_clean.csv", dtype={"review_id": str})
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["app_version"] = df["app_version"].fillna("unknown").astype(str)
    df = an.tag_reviews(df)

    an.kpi_table(df).round(2).to_csv(OUT / "kpis.csv")
    an.monthly_trends(df).round(2).to_csv(OUT / "monthly_trends.csv", index=False)
    an.topic_summary(df).round(2).to_csv(OUT / "topic_summary.csv", index=False)
    for brand in [FOCUS_BRAND, COMPETITOR]:
        slug = brand.lower()
        an.driver_analysis(df, brand).round(3).to_csv(OUT / f"drivers_{slug}.csv", index=False)
        an.churn_by_topic(df, brand).round(2).to_csv(OUT / f"churn_by_topic_{slug}.csv", index=False)
        an.release_impact(df, brand).round(2).to_csv(OUT / f"release_impact_{slug}.csv", index=False)

    lines = [f"# Recommendations for {FOCUS_BRAND} (Google Play reviews)\n"]
    for rec in an.recommendations(df, FOCUS_BRAND, COMPETITOR):
        lines += [f"## {rec['type']}: {rec['topic']}", f"- Evidence: {rec['evidence']}",
                  f"- Action: {rec['action']}", f"- Target: {rec['kpi']}", ""]
    (OUT / "recommendations.md").write_text("\n".join(lines))

    print(an.kpi_table(df).round(2).to_string())
    print(f"\nSaved analysis outputs to {OUT}/")


if __name__ == "__main__":
    main()
