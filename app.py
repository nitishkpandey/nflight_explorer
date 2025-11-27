"""
app.py

Nitish's Flight Explorer - Phase 1 (Live API)
Streamlit app that fetches real flight data from the aviationstack API.
"""

from datetime import date

import streamlit as st

from flight_api_client import AviationStackClient, FlightSearchParams, flights_to_dataframe


def configure_page() -> None:
    """Configure basic Streamlit page settings."""
    st.set_page_config(
        page_title="Nitish's Flight Explorer (Live API)",
        page_icon="✈️",
        layout="wide",
    )


@st.cache_resource
def get_api_client() -> AviationStackClient:
    """Create a single shared instance of the AviationStackClient."""
    return AviationStackClient()


@st.cache_data(ttl=300)
def fetch_flights_cached(
    flight_code: str,
    dep_iata: str,
    arr_iata: str,
    flight_date: date,
    limit: int = 25,
):
    """
    Cached wrapper around the API call so you don't burn your free
    request quota on every small UI change.
    """
    client = get_api_client()
    params = FlightSearchParams(
        flight_code=flight_code or None,
        dep_iata=dep_iata or None,
        arr_iata=arr_iata or None,
        flight_date=flight_date,
        limit=limit,
    )
    records = client.search_flights(params)
    return flights_to_dataframe(records)


def build_search_form():
    """Build the sidebar search form and return the user input."""
    st.sidebar.header("🔎 Flight Search")

    st.sidebar.markdown(
        """
        Enter **at least a flight code** (e.g. `LH760` or `760`),  
        or a combination of departure/arrival airports.
        """
    )

    flight_code = st.sidebar.text_input(
        "Flight (IATA code or number)",
        value="",
        placeholder="e.g. LH760 or 760",
    ).strip()

    dep_iata = st.sidebar.text_input(
        "Departure airport IATA (optional)",
        value="",
        placeholder="e.g. FRA",
        max_chars=3,
    ).strip().upper()

    arr_iata = st.sidebar.text_input(
        "Arrival airport IATA (optional)",
        value="",
        placeholder="e.g. DEL",
        max_chars=3,
    ).strip().upper()

    flight_date_value = st.sidebar.date_input(
        "Flight date",
        value=date.today(),
        help="For historical flights on paid plans. On free plan, this can still help narrow results.",
    )

    limit = st.sidebar.slider(
        "Max results",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
        help="Limit how many flights are returned from the API.",
    )

    search_clicked = st.sidebar.button("Search flights ✈️")

    return {
        "flight_code": flight_code,
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "flight_date": flight_date_value,
        "limit": limit,
        "search_clicked": search_clicked,
    }


def render_header() -> None:
    """Render the main page header."""
    st.title("✈️ Nitish's Flight Explorer (Live API)")
    st.markdown(
        """
        This app uses the **aviationstack** API to fetch real flight data in real time.  
        Built with **Python + Streamlit**, structured like an industry-grade project.
        """
    )
    st.markdown("---")


def render_results(df):
    """Render the search results and summary metrics."""
    if df is None:
        st.info("Use the search form on the left to query flights.")
        return

    if df.empty:
        st.warning("No flights found for your search. Try different parameters.")
        return

    st.subheader("Results")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Flights", len(df))
    with col2:
        st.metric("Airlines", df["airline_name"].nunique())
    with col3:
        st.metric("Routes", df[["dep_iata", "arr_iata"]].drop_duplicates().shape[0])

    st.markdown("### Flights table")
    st.dataframe(df, use_container_width=True)


def main() -> None:
    """Main entry point for the app."""
    configure_page()
    render_header()

    search_state = build_search_form()

    df = None
    if search_state["search_clicked"]:
        if not (
            search_state["flight_code"]
            or search_state["dep_iata"]
            or search_state["arr_iata"]
        ):
            st.error("Please provide at least a flight code or a departure/arrival airport.")
        else:
            with st.spinner("Fetching flights from aviationstack API..."):
                try:
                    df = fetch_flights_cached(
                        flight_code=search_state["flight_code"],
                        dep_iata=search_state["dep_iata"],
                        arr_iata=search_state["arr_iata"],
                        flight_date=search_state["flight_date"],
                        limit=search_state["limit"],
                    )
                except Exception as exc:
                    st.error(
                        "Failed to fetch data from aviationstack API. "
                        "Please check your internet connection, API key and free-plan limits."
                    )
                    st.exception(exc)

    render_results(df)


if __name__ == "__main__":
    main()