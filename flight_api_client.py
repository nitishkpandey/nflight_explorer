from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import logging
import requests

from config import AIRLABS_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://airlabs.co/api/v9"


@dataclass
class FlightSearchParams:
    """
    Search parameters for AirLabs real-time flights.

    We support:
    - flight_code (IATA or number)
    - dep_iata / arr_iata
    """
    flight_code: Optional[str] = None
    dep_iata: Optional[str] = None
    arr_iata: Optional[str] = None
    limit: int = 50  # AirLabs has its own limits; we’ll trim in code if needed.


class AirLabsClient:
    """Client for AirLabs real-time Flights API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 10,
    ) -> None:
        self.api_key = api_key or AIRLABS_API_KEY
        if not self.api_key:
            raise ValueError(
                "AirLabs API key is missing. "
                "Set AIRLABS_API_KEY in your environment or .env file."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Internal helper to perform a GET request and handle errors."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        query: Dict[str, Any] = {"api_key": self.api_key}
        if params:
            query.update({k: v for k, v in params.items() if v is not None})

        resp = requests.get(url, params=query, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        # AirLabs uses "error" field for problems
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            code = err.get("code", "unknown_error")
            msg = err.get("message", "Unknown AirLabs API error")
            raise RuntimeError(f"AirLabs API error ({code}): {msg}")

        return data

    def search_flights(self, params: FlightSearchParams) -> List[Dict[str, Any]]:
        """
        Call AirLabs /flights endpoint with real filters:
        - dep_iata / arr_iata
        - flight_iata / flight_number
        """
        query: Dict[str, Any] = {}

        # Route filters
        if params.dep_iata:
            query["dep_iata"] = params.dep_iata.strip().upper()
        if params.arr_iata:
            query["arr_iata"] = params.arr_iata.strip().upper()

        # Flight code filters
        if params.flight_code:
            clean = params.flight_code.strip().upper()
            if clean:
                query["flight_iata"] = clean
                numeric = "".join(ch for ch in clean if ch.isdigit())
                if numeric:
                    query["flight_number"] = numeric

        data = self._get("flights", query)

        # AirLabs usually wraps data inside "response"
        records: Any = None
        if isinstance(data, dict):
            # They sometimes use "response" or directly "data" depending on endpoint
            records = data.get("response") or data.get("data")

        if isinstance(records, list):
            flights = records
        elif isinstance(records, dict) and "flights" in records:
            flights = records["flights"]
        elif isinstance(data, list):
            flights = data
        else:
            logger.warning("Unexpected AirLabs flights response format: %s", type(data))
            flights = []

        if not isinstance(flights, list):
            return []

        # Enforce limit ourselves if needed
        if params.limit and len(flights) > params.limit:
            flights = flights[: params.limit]

        return flights


def flights_to_dataframe(records: List[Dict[str, Any]]):
    """
    Convert AirLabs flights JSON into a flat pandas DataFrame.

    Typical fields (from docs):
    hex, reg_number, flag, lat, lng, alt, dir, speed, v_speed, squawk,
    flight_number, flight_icao, flight_iata, dep_icao, dep_iata,
    arr_icao, arr_iata, airline_icao, airline_iata, aircraft_icao,
    updated, status
    """
    import pandas as pd

    rows: List[Dict[str, Any]] = []

    for item in records:
        rows.append(
            {
                "flight_iata": item.get("flight_iata"),
                "flight_number": item.get("flight_number"),
                "airline_iata": item.get("airline_iata"),
                "airline_icao": item.get("airline_icao"),
                "dep_iata": item.get("dep_iata"),
                "dep_icao": item.get("dep_icao"),
                "arr_iata": item.get("arr_iata"),
                "arr_icao": item.get("arr_icao"),
                "status": item.get("status"),
                "lat": item.get("lat"),
                "lng": item.get("lng"),
                "alt": item.get("alt"),
                "speed": item.get("speed"),
                "dir": item.get("dir"),
                "updated": item.get("updated"),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        sort_cols = [c for c in ["dep_iata", "arr_iata", "airline_iata", "flight_number"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols)

    return df