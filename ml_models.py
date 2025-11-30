from __future__ import annotations

from typing import Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


def cluster_flights_by_alt_speed(
    df: pd.DataFrame,
    n_clusters: int = 3,
) -> Tuple[pd.DataFrame, Optional[KMeans]]:
    """
    Given a flights DataFrame with 'alt' and 'speed' columns,
    perform KMeans clustering on those two features.

    Returns:
        - df_with_clusters: copy of df with a new 'cluster' column.
        - model: fitted KMeans model (or None if clustering was not possible).
    """
    df = df.copy()

    # Ensure required columns exist
    if "alt" not in df.columns or "speed" not in df.columns:
        df["cluster"] = np.nan
        return df, None

    # Use only rows with non-null alt & speed
    mask = df["alt"].notna() & df["speed"].notna()
    if mask.sum() < n_clusters:
        # Not enough data points to form clusters
        df["cluster"] = np.nan
        return df, None

    feature_data = df.loc[mask, ["alt", "speed"]].astype(float)

    # Scale features for better clustering
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(feature_data)

    # Fit KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    cluster_labels = kmeans.fit_predict(X_scaled)

    # Assign cluster labels back to df
    df.loc[mask, "cluster"] = cluster_labels
    df.loc[~mask, "cluster"] = np.nan

    # Convert to int where possible
    df["cluster"] = df["cluster"].astype("Int64")

    return df, kmeans