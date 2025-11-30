"""
db.py

SQLite storage for Nitish's Flight Explorer:
- searches table: each search the user performs
- flights table: snapshot of flights returned for that search
- analytics helpers: aggregate stats for routes, airlines, searches, and alt/speed
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, List

import sqlite3
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "flights.db"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    # Searches table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            searched_at TEXT NOT NULL,
            dep_iata TEXT,
            arr_iata TEXT,
            flight_code TEXT,
            limit_value INTEGER,
            results_count INTEGER
        );
        """
    )

    # Flights table, linked to searches
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS flights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL,
            flight_iata TEXT,
            flight_number TEXT,
            airline_iata TEXT,
            airline_icao TEXT,
            dep_iata TEXT,
            dep_icao TEXT,
            arr_iata TEXT,
            arr_icao TEXT,
            status TEXT,
            lat REAL,
            lng REAL,
            alt REAL,
            speed REAL,
            dir REAL,
            updated TEXT,
            FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE
        );
        """
    )

    conn.commit()
    conn.close()


def log_search_and_flights(
    dep_iata: Optional[str],
    arr_iata: Optional[str],
    flight_code: Optional[str],
    limit_value: int,
    flights_df: pd.DataFrame,
) -> int:
    """
    Insert one row into searches and corresponding rows into flights.

    Returns the search_id.
    """
    conn = get_connection()
    cur = conn.cursor()

    searched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    results_count = int(len(flights_df)) if flights_df is not None else 0

    # Insert into searches
    cur.execute(
        """
        INSERT INTO searches (searched_at, dep_iata, arr_iata, flight_code, limit_value, results_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (searched_at, dep_iata, arr_iata, flight_code, limit_value, results_count),
    )
    search_id = cur.lastrowid

    # Insert flights if any
    if results_count > 0:
        rows_to_insert: List[tuple] = []
        for _, row in flights_df.iterrows():
            rows_to_insert.append(
                (
                    search_id,
                    row.get("flight_iata"),
                    row.get("flight_number"),
                    row.get("airline_iata"),
                    row.get("airline_icao"),
                    row.get("dep_iata"),
                    row.get("dep_icao"),
                    row.get("arr_iata"),
                    row.get("arr_icao"),
                    row.get("status"),
                    row.get("lat"),
                    row.get("lng"),
                    row.get("alt"),
                    row.get("speed"),
                    row.get("dir"),
                    row.get("updated"),
                )
            )

        cur.executemany(
            """
            INSERT INTO flights (
                search_id,
                flight_iata,
                flight_number,
                airline_iata,
                airline_icao,
                dep_iata,
                dep_icao,
                arr_iata,
                arr_icao,
                status,
                lat,
                lng,
                alt,
                speed,
                dir,
                updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )

    conn.commit()
    conn.close()
    return search_id


def get_recent_searches(limit: int = 10) -> pd.DataFrame:
    """Return the most recent searches as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            id,
            searched_at,
            dep_iata,
            arr_iata,
            flight_code,
            limit_value,
            results_count
        FROM searches
        ORDER BY searched_at DESC
        LIMIT ?
        """,
        conn,
        params=(limit,),
    )
    conn.close()
    return df


# ---------------------- Analytics helpers (Phase 3) ---------------------- #


def get_route_stats(limit: int = 10) -> pd.DataFrame:
    """
    Return top routes by number of flights observed.
    One row per (dep_iata, arr_iata).
    """
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            dep_iata,
            arr_iata,
            COUNT(*) AS flights_count,
            COUNT(DISTINCT airline_iata) AS airlines_count
        FROM flights
        WHERE dep_iata IS NOT NULL
          AND arr_iata IS NOT NULL
        GROUP BY dep_iata, arr_iata
        ORDER BY flights_count DESC
        LIMIT ?
        """,
        conn,
        params=(limit,),
    )
    conn.close()

    if not df.empty:
        df["route"] = df["dep_iata"].fillna("?") + " → " + df["arr_iata"].fillna("?")
    return df


def get_airline_stats(limit: int = 10) -> pd.DataFrame:
    """
    Return top airlines by number of flights seen in our data.
    """
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            airline_iata,
            airline_icao,
            COUNT(*) AS flights_count,
            COUNT(DISTINCT dep_iata || '-' || arr_iata) AS routes_count
        FROM flights
        WHERE airline_iata IS NOT NULL
        GROUP BY airline_iata, airline_icao
        ORDER BY flights_count DESC
        LIMIT ?
        """,
        conn,
        params=(limit,),
    )
    conn.close()
    return df


def get_searches_by_day() -> pd.DataFrame:
    """
    Aggregate searches per day.
    searched_at is ISO string, so we can take first 10 chars as date.
    """
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            substr(searched_at, 1, 10) AS date,
            COUNT(*) AS search_count,
            SUM(results_count) AS total_results
        FROM searches
        GROUP BY date
        ORDER BY date
        """,
        conn,
    )
    conn.close()
    return df


def get_altitude_speed_distribution() -> pd.DataFrame:
    """
    Return alt + speed columns for flights where both are present.
    Useful for scatter/histograms.
    """
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            alt,
            speed
        FROM flights
        WHERE alt IS NOT NULL
          AND speed IS NOT NULL
        """,
        conn,
    )
    conn.close()
    return df


# Initialize DB on import
init_db()