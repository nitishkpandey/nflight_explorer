"""
app.py

N's Flight Explorer - Live Flights UI + SQLite history
"""

from datetime import date

import streamlit as st

from flight_api_client import AirLabsClient, FlightSearchParams, flights_to_dataframe
from db import (
    log_search_and_flights,
    get_recent_searches,
    get_route_stats,
    get_airline_stats,
    get_searches_by_day,
    get_altitude_speed_distribution,
)
from ml_models import cluster_flights_by_alt_speed

# ---------------------------- Page & Style ---------------------------- #

def configure_page() -> None:
    st.set_page_config(
        page_title="Nitish's Flight Explorer",
        page_icon="✈️",
        layout="wide",
    )

    # Light custom CSS to make it feel closer to a real product UI
    st.markdown(
        """
        <style>
        /* Overall background */
        .stApp {
            background-color: #f5f7fb;
        }

        /* Main title spacing */
        .app-title {
            font-size: 2.4rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }

        .app-subtitle {
            font-size: 1rem;
            color: #6b7280;
            margin-bottom: 1.5rem;
        }

        /* Card style containers */
        .card {
            background-color: #ffffff;
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.07);
            border: 1px solid #e5e7eb;
        }

        .search-card {
            margin-top: 0.5rem;
            margin-bottom: 1.5rem;
        }

        .metric-chip {
            background-color: #f3f4ff;
            border-radius: 999px;
            padding: 0.5rem 1rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.9rem;
        }

        .metric-label {
            color: #6b7280;
            font-weight: 500;
        }

        .metric-value {
            font-weight: 700;
            color: #111827;
        }

        .section-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
        }

        .stButton>button {
            border-radius: 999px;
            padding: 0.5rem 1.25rem;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------- API Layer ---------------------------- #


@st.cache_resource
def get_api_client() -> AirLabsClient:
    """Create a single shared instance of the AirLabsClient."""
    return AirLabsClient()


@st.cache_data(ttl=60)
def fetch_flights_cached(
    flight_code: str,
    dep_iata: str,
    arr_iata: str,
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
        limit=limit,
    )
    records = client.search_flights(params)
    return flights_to_dataframe(records)


# ---------------------------- UI Building Blocks ---------------------------- #


def render_header() -> None:
    """Top hero header."""
    col_logo, col_title = st.columns([0.1, 0.9])

    with col_logo:
        st.markdown("### ✈️")

    with col_title:
        st.markdown('<div class="app-title">Nitish\'s Flight Explorer</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="app-subtitle">'
            "Search and explore live flights by route or flight code, "
            "powered by a real-time flights API and built with Python + Streamlit."
            "</div>",
            unsafe_allow_html=True,
        )


def build_search_card():
    """
    Centered search card at the top.
    Returns a dict of search parameters and a flag if search was triggered.
    """
    st.markdown('<div class="card search-card">', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Search flights</div>', unsafe_allow_html=True)

    col1, col2, col3, col4, col5 = st.columns([1.3, 1, 1, 1, 0.8])

    with col1:
        flight_code = st.text_input(
            "Flight (IATA or number)",
            value="",
            placeholder="e.g. LH760 or 760",
        ).strip()

    with col2:
        dep_iata = st.text_input(
            "Departure IATA",
            value="",
            placeholder="e.g. FRA",
            max_chars=3,
        ).strip().upper()

    with col3:
        arr_iata = st.text_input(
            "Arrival IATA",
            value="",
            placeholder="e.g. BER",
            max_chars=3,
        ).strip().upper()

    with col4:
        _flight_date = st.date_input(
            "Date (info only)",
            value=date.today(),
            help="Current API returns live flights; date is reserved for future features.",
        )

    with col5:
        limit = st.slider(
            "Max results",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            label_visibility="visible",
        )

    col_btn = st.columns([0.8, 0.4, 0.8])[1]
    with col_btn:
        search_clicked = st.button("🔍 Search flights", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "flight_code": flight_code,
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "limit": limit,
        "search_clicked": search_clicked,
    }


def render_metrics(df):
    """Render the top summary metrics in chip style."""
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Results</div>', unsafe_allow_html=True)

    if df is None:
        st.info("Search for a route or flight to see live results.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if df.empty:
        st.warning("No flights found for your search. Try different parameters.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    flights_count = len(df)
    airlines_count = df["airline_iata"].nunique() if "airline_iata" in df.columns else 0
    routes_count = (
        df[["dep_iata", "arr_iata"]].dropna().drop_duplicates().shape[0]
        if {"dep_iata", "arr_iata"}.issubset(df.columns)
        else 0
    )
    cluster_count = df["cluster"].nunique(dropna=True) if "cluster" in df.columns else 0
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="metric-chip">'
            f'<span class="metric-label">Flights</span>'
            f'<span class="metric-value">{flights_count}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="metric-chip">'
            f'<span class="metric-label">Airlines</span>'
            f'<span class="metric-value">{airlines_count}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="metric-chip">'
            f'<span class="metric-label">Routes</span>'
            f'<span class="metric-value">{routes_count}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="metric-chip">'
            f'<span class="metric-label">Clusters</span>'
            f'<span class="metric-value">{cluster_count}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_results(df):
    """Render main results table + optional details panel."""
    if df is None or df.empty:
        return

    st.markdown('<div class="card" style="margin-top:1rem;">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Flights table</div>', unsafe_allow_html=True)

    col_table, col_details = st.columns([1.8, 1.2])

    with col_table:
        st.dataframe(df, use_container_width=True, height=420)

    with col_details:
        st.markdown('<div class="section-title">Flight details</div>', unsafe_allow_html=True)

        index_options = list(df.index)
        if not index_options:
            st.info("No flights to show.")
        else:
            selected_index = st.selectbox(
                "Select a flight:",
                options=index_options,
                format_func=lambda idx: f"{df.loc[idx].get('flight_iata') or df.loc[idx].get('flight_number') or 'Flight'}"
                                        f" | {df.loc[idx].get('dep_iata', '')} → {df.loc[idx].get('arr_iata', '')}",
            )
            row = df.loc[selected_index]

            st.markdown(
                f"""
                **Flight:** {row.get('flight_iata') or row.get('flight_number') or 'N/A'}  
                **Airline:** {row.get('airline_iata') or row.get('airline_icao') or 'N/A'}  
                **Route:** {row.get('dep_iata', '???')} → {row.get('arr_iata', '???')}  
                **Status:** {row.get('status', 'N/A')}  
                **Updated:** {row.get('updated', 'N/A')}  
                """,
            )

            with st.expander("Raw record (for debugging / data understanding)"):
                st.json(row.to_dict())

    st.markdown("</div>", unsafe_allow_html=True)

def render_analytics_section() -> None:
    """
    Show basic analytics using the stored SQLite data.
    - Top routes
    - Top airlines
    - Searches over time
    - Altitude vs speed distribution
    """
    # Top routes
    st.markdown("#### Top routes (by number of flights)")
    try:
        routes_df = get_route_stats(limit=10)
        if routes_df.empty:
            st.info("Not enough route data yet. Run a few searches first.")
        else:
            st.dataframe(routes_df[["route", "flights_count", "airlines_count"]], use_container_width=True)

            # Simple bar chart by flights_count
            chart_data = routes_df.set_index("route")[["flights_count"]]
            st.bar_chart(chart_data)
    except Exception as exc:
        st.warning("Failed to load route statistics.")
        st.exception(exc)

    st.markdown("---")

    # Top airlines
    st.markdown("#### Top airlines (by flights observed)")
    try:
        airlines_df = get_airline_stats(limit=10)
        if airlines_df.empty:
            st.info("Not enough airline data yet.")
        else:
            st.dataframe(
                airlines_df[["airline_iata", "airline_icao", "flights_count", "routes_count"]],
                use_container_width=True,
            )

            chart_data = airlines_df.set_index("airline_iata")[["flights_count"]]
            st.bar_chart(chart_data)
    except Exception as exc:
        st.warning("Failed to load airline statistics.")
        st.exception(exc)

    st.markdown("---")

    # Searches over time
    st.markdown("#### Searches over time")
    try:
        searches_df = get_searches_by_day()
        if searches_df.empty:
            st.info("No search history yet.")
        else:
            st.dataframe(searches_df, use_container_width=True)

            chart_data = searches_df.set_index("date")[["search_count"]]
            st.line_chart(chart_data)
    except Exception as exc:
        st.warning("Failed to load search history statistics.")
        st.exception(exc)

    st.markdown("---")

    # Altitude vs speed
    st.markdown("#### Altitude vs speed distribution")
    try:
        alt_speed_df = get_altitude_speed_distribution()
        if alt_speed_df.empty or len(alt_speed_df) < 5:
            st.info("Not enough data to show altitude/speed distribution yet.")
        else:
            st.dataframe(alt_speed_df.head(20), use_container_width=True)
            st.scatter_chart(alt_speed_df, x="speed", y="alt")
    except Exception as exc:
        st.warning("Failed to load altitude/speed data.")
        st.exception(exc)
    
        st.markdown("---")
    st.markdown("#### Clusters (current stored flights sample)")

    try:
        # Reuse altitude/speed data with clusters if available
        # We'll just pull from DB directly using helper again
        alt_speed_df = get_altitude_speed_distribution()
        if alt_speed_df.empty:
            st.info("Not enough data to show clusters yet.")
        else:
            # We need full flights data with cluster info from DB for a proper plot,
            # but as a simple version we can just explain that clustering
            # is applied on each search in the main view.
            st.info(
                "Clustering is applied on each search in the main view. "
                "You can explore clusters via the flights table and metrics above."
            )
    except Exception as exc:
        st.warning("Failed to load data for cluster analytics.")
        st.exception(exc)

# ---------------------------- Main ---------------------------- #
def main() -> None:
    configure_page()
    render_header()

    search_state = build_search_card()

    df = None

    if search_state["search_clicked"]:
        # If user provided any filter -> filtered search
        if (
            search_state["flight_code"]
            or search_state["dep_iata"]
            or search_state["arr_iata"]
        ):
            info_text = "Fetching filtered flights from live flights API..."
        else:
            # No filters at all -> global snapshot
            info_text = (
                "No filters provided. Showing a global snapshot of live flights "
                f"(up to {search_state['limit']})."
            )
            st.info(info_text)

        with st.spinner("Fetching flights from live flights API..."):
            try:
                # Fetch from API – note: if everything is empty, this becomes a global snapshot
                df = fetch_flights_cached(
                    flight_code=search_state["flight_code"],
                    dep_iata=search_state["dep_iata"],
                    arr_iata=search_state["arr_iata"],
                    limit=search_state["limit"],
                )
                # ---- Phase 4A: cluster flights by altitude & speed ----
                if df is not None and not df.empty:
                    try:
                        df, _ = cluster_flights_by_alt_speed(df, n_clusters=3)
                    except Exception as ml_exc:
                        st.warning("Failed to cluster flights (ML step).")
                        st.exception(ml_exc)

                # Log to SQLite (even if it's global snapshot)
                if df is not None:
                    try:
                        log_search_and_flights(
                            dep_iata=search_state["dep_iata"],
                            arr_iata=search_state["arr_iata"],
                            flight_code=search_state["flight_code"],
                            limit_value=search_state["limit"],
                            flights_df=df,
                        )
                    except Exception as db_exc:
                        st.warning(
                            "Search worked, but failed to save to history database."
                        )
                        st.exception(db_exc)

            except Exception as exc:
                st.error(
                    "Failed to fetch data from the flights API. "
                    "Please check your internet connection and API key."
                )
                st.exception(exc)

    # Show metrics + results for current search
    render_metrics(df)
    render_results(df)

    # Recent search history from SQLite
    with st.expander("Recent searches (from SQLite history)", expanded=False):
        try:
            history_df = get_recent_searches(limit=10)
            if history_df.empty:
                st.info("No searches stored yet.")
            else:
                st.dataframe(history_df, use_container_width=True)
        except Exception as exc:
            st.warning("Failed to load recent searches from the database.")
            st.exception(exc)

    # Analytics section (Phase 3)
    with st.expander("Analytics & insights (from stored history)", expanded=False):
        render_analytics_section()
if __name__ == "__main__":
    main()