from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import logging
import requests

from config import AVIATIONSTACK_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "http://api.aviationstack.com/v1"


@dataclass
class FlightSearchParams:
    """Strongly-typed search parameters for the Flights endpoint."""
    flight_code: Optional[str] = None
    dep_iata: Optional[str] = None
    arr_iata: Optional[str] = None
    flight_date: Optional[date] = None
    limit: int = 25


class AviationStackClient:
    """Thin client wrapper around the aviationstack Flights endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 10,
    ) -> None:
        self.api_key = api_key or AVIATIONSTACK_API_KEY
        if not self.api_key:
            raise ValueError(
                "Aviationstack API key is missing. "
                "Set AVIATIONSTACK_API_KEY in your environment or .env file."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Internal helper to perform a GET request and handle errors."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        query: Dict[str, Any] = {"access_key": self.api_key}
        if params:
            query.update({k: v for k, v in params.items() if v is not None})

        response = requests.get(url, params=query, timeout=self.timeout)

        # Try to parse JSON first
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            return {}

        # HTTP-level errors
        if response.status_code >= 400:
            if isinstance(data, dict) and "error" in data:
                err = data["error"] or {}
                code = err.get("code") or "unknown_error"
                msg = err.get("message") or "Unknown API error"
                raise RuntimeError(f"Aviationstack API error ({code}): {msg}")
            response.raise_for_status()

        # aviationstack internal errors
        if isinstance(data, dict) and data.get("success") is False:
            error_info = data.get("error") or {}
            message = error_info.get("info") or error_info.get("message") or "Unknown API error"
            raise RuntimeError(f"Aviationstack API error: {message}")

        return data

    def search_flights(self, params: FlightSearchParams) -> List[Dict[str, Any]]:
        """Free plan safe API request."""
        query: Dict[str, Any] = {"limit": params.limit}

        if params.flight_code:
            clean = params.flight_code.strip().upper()
            if clean:
                query["flight_iata"] = clean
                numeric = "".join(ch for ch in clean if ch.isdigit())
                if numeric:
                    query["flight_number"] = numeric

        # Do NOT send dep_iata, arr_iata, or flight_date (free plan limitation)

        data = self._get("flights", query)
        return data.get("data") or []


def flights_to_dataframe(records: List[Dict[str, Any]]):
    """Convert API JSON to DataFrame."""
    import pandas as pd

    rows = []
    for item in records:
        departure = item.get("departure") or {}
        arrival = item.get("arrival") or {}
        airline = item.get("airline") or {}
        flight = item.get("flight") or {}

        rows.append({
            "flight_date": item.get("flight_date"),
            "flight_status": item.get("flight_status"),
            "airline_name": airline.get("name"),
            "airline_iata": airline.get("iata"),
            "flight_number": flight.get("number"),
            "flight_iata": flight.get("iata"),
            "dep_airport": departure.get("airport"),
            "dep_iata": departure.get("iata"),
            "dep_scheduled": departure.get("scheduled"),
            "dep_actual": departure.get("actual"),
            "arr_airport": arrival.get("airport"),
            "arr_iata": arrival.get("iata"),
            "arr_scheduled": arrival.get("scheduled"),
            "arr_actual": arrival.get("actual"),
        })

    return pd.DataFrame(rows)