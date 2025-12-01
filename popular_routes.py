"""
popular_routes.py

Phase 4B – Popular Route Prediction using frequency + recency weighting.
Uses the 'searches' table from SQLite.
"""

from __future__ import annotations

from typing import List, Tuple

import pandas as pd
from db import get_connection


def load_search_history() -> pd.DataFrame:
    """Load all searches as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            searched_at,
            dep_iata,
            arr_iata
        FROM searches
        WHERE dep_iata IS NOT NULL
          AND arr_iata IS NOT NULL
        """,
        conn,
    )
    conn.close()

    if df.empty:
        return df

    # Parse timestamps as UTC-aware
    df["searched_at"] = pd.to_datetime(df["searched_at"], errors="coerce", utc=True)

    # Drop rows where timestamp parsing failed
    df = df.dropna(subset=["searched_at"])

    return df


def compute_popular_routes(df: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    """
    Compute route popularity based on frequency + recency weighting.
    Routes searched more recently get higher weight.
    """

    if df.empty:
        return pd.DataFrame(columns=["route", "score", "count", "last_searched"])

    df = df.copy()

    # Create "route" column
    df["route"] = df["dep_iata"] + " → " + df["arr_iata"]

    # 1. Count how many times each route appears
    count_df = df.groupby("route").size().reset_index(name="count")

    # 2. Recency score — recent searches get higher points
    # Use a UTC-aware "now" to match the UTC-aware searched_at
    now = pd.Timestamp.now(tz="UTC")
    df["age_minutes"] = (now - df["searched_at"]).dt.total_seconds() / 60

    # Avoid negative or weird values just in case
    df["age_minutes"] = df["age_minutes"].clip(lower=0)

    # Decay every 30 minutes: newer searches → higher recency_score
    df["recency_score"] = df["age_minutes"].apply(
        lambda x: max(0.1, 1 / (1 + x / 30.0))
    )

    recency_df = df.groupby("route")["recency_score"].sum().reset_index()

    # 3. Combine (frequency + recency)
    merged = count_df.merge(recency_df, on="route", how="left")

    # Weighted score: 70% frequency, 30% recency
    merged["score"] = 0.7 * merged["count"] + 0.3 * merged["recency_score"]

    # Last searched time
    last_df = df.groupby("route")["searched_at"].max().reset_index()
    last_df.rename(columns={"searched_at": "last_searched"}, inplace=True)

    merged = merged.merge(last_df, on="route", how="left")

    # Sort by score
    merged = merged.sort_values("score", ascending=False)

    return merged.head(top_k)