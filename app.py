from __future__ import annotations

import json
import re
import base64
import binascii
import hashlib
import hmac
import secrets
import time
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import altair as alt
import pandas as pd
import streamlit as st
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow


SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
ANALYTICS_API_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"
CONTENT_TYPES = ["Shorts", "Videos", "Lives", "Podcasts"]
CONTENT_COLORS = {
    "Shorts": "#8f73ff",
    "Videos": "#48d921",
    "Lives": "#ffb000",
    "Podcasts": "#31b6ff",
}


def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except FileNotFoundError:
        return default


def toml_table(name: str, values: dict[str, Any]) -> str:
    lines = [f"[{name}]"]
    for key, value in values.items():
        if value is None:
            continue
        encoded = str(value).lower() if isinstance(value, bool) else json.dumps(value)
        lines.append(f"{key} = {encoded}")
    return "\n".join(lines)


def youtube_token_secrets() -> dict[str, Any]:
    token = secret("youtube_oauth_token")
    if token:
        return dict(token)

    legacy = secret("youtube")
    if legacy:
        return dict(legacy)

    raise RuntimeError(
        "Missing YouTube token in Streamlit Secrets. Add a [youtube_oauth_token] "
        "section, or use Reconnect YouTube to generate one."
    )


def youtube_settings() -> dict[str, Any]:
    settings = secret("youtube")
    if not settings:
        raise RuntimeError(
            "Missing Streamlit secrets section [youtube]. Add podcast_playlist_id."
        )
    return dict(settings)


def make_credentials() -> Credentials:
    token = youtube_token_secrets()
    credentials = Credentials(
        token=token.get("token"),
        refresh_token=token.get("refresh_token"),
        token_uri=token.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token["client_id"],
        client_secret=token["client_secret"],
        scopes=token.get("scopes", SCOPES),
    )
    try:
        credentials.refresh(GoogleAuthRequest())
    except RefreshError as error:
        raise RuntimeError(
            "YouTube authorization expired or was revoked. Open Reconnect YouTube "
            "from the left menu, sign in with the YouTube channel owner or manager "
            "account, then replace the [youtube_oauth_token] block in Streamlit Secrets."
        ) from error
    return credentials


def youtube_web_oauth_settings() -> tuple[dict[str, Any], str]:
    client = secret("youtube_web_oauth_client")
    redirect_uri = str(secret("youtube_redirect_uri", "")).strip()
    if client and redirect_uri:
        return dict(client), redirect_uri

    legacy = secret("youtube")
    if legacy and not redirect_uri:
        redirect_uri = str(legacy.get("youtube_redirect_uri") or legacy.get("redirect_uri") or "").strip()
    if legacy and legacy.get("client_id") and legacy.get("client_secret") and redirect_uri:
        return {
            "client_id": legacy["client_id"],
            "client_secret": legacy["client_secret"],
            "auth_uri": legacy.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": legacy.get("token_uri", "https://oauth2.googleapis.com/token"),
        }, redirect_uri

    raise RuntimeError(
        "Reconnect YouTube is not set up yet. Add youtube_redirect_uri and "
        "[youtube_web_oauth_client] to Streamlit Secrets."
    )


def youtube_oauth_state(client_secret: str, code_verifier: str) -> str:
    payload = json.dumps(
        {
            "created_at": int(time.time()),
            "nonce": secrets.token_urlsafe(24),
            "code_verifier": code_verifier,
        },
        separators=(",", ":"),
    )
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(client_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def youtube_oauth_code_verifier(state: str, client_secret: str) -> str | None:
    try:
        encoded, signature = state.rsplit(".", 1)
        expected = hmac.new(client_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding).decode())
        created_at = int(payload["created_at"])
        code_verifier = str(payload["code_verifier"])
        if not 0 <= time.time() - created_at <= 900:
            return None
        if not 43 <= len(code_verifier) <= 128:
            return None
        return code_verifier
    except (binascii.Error, KeyError, ValueError, TypeError, UnicodeDecodeError):
        return None


def render_youtube_reconnect_page() -> None:
    st.title("Reconnect YouTube")
    st.write(
        "Use this page when the dashboard says YouTube authorization expired or was revoked."
    )
    st.warning(
        "Streamlit cannot update saved Secrets by itself. This page creates a "
        "replacement token block that an administrator must copy into Streamlit Secrets."
    )

    try:
        client, redirect_uri = youtube_web_oauth_settings()
    except RuntimeError as error:
        st.error(str(error))
        st.info("See the README section about reconnecting YouTube for the one-time setup.")
        return

    code = st.query_params.get("code")
    returned_state = st.query_params.get("state")
    oauth_error = st.query_params.get("error")
    if oauth_error:
        st.error(f"Google did not authorize YouTube: {oauth_error}")
        st.query_params.clear()
        return

    if code:
        client_secret = str(client.get("client_secret", ""))
        code_verifier = (
            youtube_oauth_code_verifier(returned_state, client_secret)
            if returned_state
            else None
        )
        if not code_verifier:
            st.error("The authorization session could not be verified. Start YouTube sign-in again.")
            st.query_params.clear()
            return
        try:
            flow = Flow.from_client_config(
                {"web": client},
                scopes=SCOPES,
                state=returned_state,
                autogenerate_code_verifier=False,
            )
            flow.redirect_uri = redirect_uri
            flow.code_verifier = code_verifier
            flow.fetch_token(code=code)
            token_values = json.loads(flow.credentials.to_json())
        except Exception as error:
            st.query_params.clear()
            st.error(f"Google returned authorization, but the new token could not be created: {error}")
            return

        st.query_params.clear()
        token_toml = toml_table("youtube_oauth_token", token_values)
        st.success("YouTube authorization succeeded. Complete the steps below.")
        st.code(token_toml, language="toml")
        st.download_button(
            "Download replacement token block",
            data=token_toml,
            file_name="youtube-token-for-streamlit.toml",
            mime="text/plain",
        )
        st.markdown(
            "1. Open this app in Streamlit Cloud and choose **Manage app**.\n"
            "2. Open **Settings**, then **Secrets**.\n"
            "3. Replace the entire existing `[youtube_oauth_token]` section with the block above.\n"
            "4. Save, wait for the app to restart, and return to the dashboard."
        )
        return

    if st.button("Start YouTube sign-in", type="primary", use_container_width=True):
        flow = Flow.from_client_config(
            {"web": client},
            scopes=SCOPES,
            autogenerate_code_verifier=False,
        )
        flow.redirect_uri = redirect_uri
        code_verifier = secrets.token_urlsafe(64)
        flow.code_verifier = code_verifier
        state = youtube_oauth_state(str(client.get("client_secret", "")), code_verifier)
        authorization_url, _ = flow.authorization_url(
            state=state,
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        st.link_button(
            "Continue to Google",
            authorization_url,
            type="primary",
            use_container_width=True,
        )
        st.caption("Sign in with the Google account that owns or manages the YouTube channel.")


def authed_get_json(credentials: Credentials, url: str, params: dict[str, Any]) -> dict[str, Any]:
    if not credentials.valid:
        credentials.refresh(GoogleAuthRequest())

    query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
    request = Request(
        f"{url}?{query}",
        headers={"Authorization": f"Bearer {credentials.token}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(youtube_api_error_message(error)) from error
    except URLError as error:
        raise RuntimeError(f"YouTube connection error: {error.reason}") from error


def youtube_api_error_message(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8")
    except Exception:
        body = ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}

    api_error = payload.get("error", {})
    message = api_error.get("message") or body or error.reason
    if message == "Forbidden":
        message = (
            "Forbidden. Confirm the Google account has access to the YouTube channel "
            "and that YouTube Analytics API and YouTube Data API v3 are enabled."
        )
    return f"YouTube API error {error.code}: {message}"


def iso_duration_seconds(value: str | None) -> int:
    if not value:
        return 0
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?"
        r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value,
    )
    if not match:
        return 0
    parts = {key: int(raw or 0) for key, raw in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def report_rows(
    credentials: Credentials,
    start_date: date,
    end_date: date,
    *,
    dimensions: str,
    filters: str | None = None,
    sort: str | None = None,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    start_index = 1
    page_size = 200
    headers: list[str] = []

    while True:
        response = authed_get_json(
            credentials,
            ANALYTICS_API_URL,
            {
                "ids": "channel==MINE",
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "metrics": "views,estimatedMinutesWatched,averageViewDuration",
                "dimensions": dimensions,
                "filters": filters,
                "sort": sort,
                "startIndex": start_index,
                "maxResults": page_size,
            },
        )
        if not headers:
            headers = [item["name"] for item in response.get("columnHeaders", [])]
        page_rows = response.get("rows") or []
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start_index += page_size

    return pd.DataFrame(rows, columns=headers)


def playlist_video_ids(credentials: Credentials, playlist_id: str) -> set[str]:
    video_ids: set[str] = set()
    page_token = None
    while True:
        response = authed_get_json(
            credentials,
            f"{YOUTUBE_API_URL}/playlistItems",
            {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
                "pageToken": page_token,
            },
        )
        for item in response.get("items") or []:
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id:
                video_ids.add(video_id)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def video_metadata(credentials: Credentials, video_ids: list[str]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for chunk in chunked(video_ids, 50):
        response = authed_get_json(
            credentials,
            f"{YOUTUBE_API_URL}/videos",
            {
                "part": "snippet,contentDetails,liveStreamingDetails",
                "id": ",".join(chunk),
                "maxResults": 50,
            },
        )
        for item in response.get("items") or []:
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            records.append(
                {
                    "video_id": item.get("id"),
                    "title": snippet.get("title", ""),
                    "duration_seconds": iso_duration_seconds(content.get("duration")),
                    "is_live": bool(item.get("liveStreamingDetails")),
                }
            )
    return pd.DataFrame(records)


def video_total_rows(
    credentials: Credentials,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    raw_df = report_rows(
        credentials,
        start_date,
        end_date,
        dimensions="video",
        sort="-views",
    )
    if raw_df.empty:
        return pd.DataFrame(
            columns=["video_id", "views", "watch_minutes", "avg_view_duration_seconds"]
        )

    df = raw_df.rename(
        columns={
            "video": "video_id",
            "estimatedMinutesWatched": "watch_minutes",
            "averageViewDuration": "avg_view_duration_seconds",
        }
    )
    df["views"] = pd.to_numeric(df["views"], errors="coerce").fillna(0).astype(int)
    df["watch_minutes"] = pd.to_numeric(df["watch_minutes"], errors="coerce").fillna(0.0)
    df["avg_view_duration_seconds"] = pd.to_numeric(
        df["avg_view_duration_seconds"], errors="coerce"
    ).fillna(0.0)
    return df


def classify_content(
    analytics_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    podcast_video_ids: set[str],
) -> pd.DataFrame:
    if analytics_df.empty:
        return analytics_df.assign(content_type=pd.Series(dtype="string"))

    df = analytics_df.merge(metadata_df, on="video_id", how="left")
    df["duration_seconds"] = pd.to_numeric(
        df["duration_seconds"], errors="coerce"
    ).fillna(0).astype(int)
    df["title"] = df["title"].fillna("Unknown video")
    df["is_live"] = df["is_live"].fillna(False).astype(bool)

    def classify(row: pd.Series) -> str:
        if row["video_id"] in podcast_video_ids:
            return "Podcasts"
        if row["is_live"]:
            return "Lives"
        if row["duration_seconds"] <= 60:
            return "Shorts"
        return "Videos"

    df["content_type"] = df.apply(classify, axis=1)
    return df


def video_ids_daily_rows(
    credentials: Credentials,
    start_date: date,
    end_date: date,
    video_ids: list[str],
    content_type: str,
) -> pd.DataFrame:
    frames = []
    for chunk in chunked(video_ids, 500):
        raw_df = report_rows(
            credentials,
            start_date,
            end_date,
            dimensions="day",
            filters=f"video=={','.join(chunk)}",
            sort="day",
        )
        if not raw_df.empty:
            frames.append(raw_df)

    if not frames:
        return pd.DataFrame(
            columns=[
                "date",
                "content_type",
                "views",
                "watch_minutes",
                "avg_view_duration_seconds",
            ]
        )

    df = pd.concat(frames, ignore_index=True).rename(
        columns={
            "day": "date",
            "estimatedMinutesWatched": "watch_minutes",
            "averageViewDuration": "avg_view_duration_seconds",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    df["views"] = pd.to_numeric(df["views"], errors="coerce").fillna(0).astype(int)
    df["watch_minutes"] = pd.to_numeric(df["watch_minutes"], errors="coerce").fillna(0.0)
    df["avg_view_duration_seconds"] = pd.to_numeric(
        df["avg_view_duration_seconds"], errors="coerce"
    ).fillna(0.0)
    df["content_type"] = content_type
    return (
        df.groupby(["date", "content_type"], as_index=False)
        .agg(
            views=("views", "sum"),
            watch_minutes=("watch_minutes", "sum"),
            avg_view_duration_seconds=("avg_view_duration_seconds", "mean"),
        )
        .sort_values("date")
    )


def complete_daily_frame(daily_df: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    scaffold = pd.MultiIndex.from_product(
        [pd.date_range(start_date, end_date, freq="D"), CONTENT_TYPES],
        names=["date", "content_type"],
    ).to_frame(index=False)
    return scaffold.merge(daily_df, on=["date", "content_type"], how="left").fillna(
        {
            "views": 0,
            "watch_minutes": 0.0,
            "avg_view_duration_seconds": 0.0,
        }
    )


@st.cache_data(ttl=900, show_spinner=False)
def load_dashboard_data(start_date: date, end_date: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    credentials = make_credentials()
    settings = youtube_settings()
    podcast_playlist_id = settings["podcast_playlist_id"]

    totals_df = video_total_rows(credentials, start_date, end_date)
    if totals_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    podcast_ids = playlist_video_ids(credentials, podcast_playlist_id)
    metadata_df = video_metadata(credentials, sorted(totals_df["video_id"].dropna().unique()))
    detail_df = classify_content(totals_df, metadata_df, podcast_ids)

    daily_frames = []
    for content_type in CONTENT_TYPES:
        ids = sorted(
            detail_df.loc[detail_df["content_type"] == content_type, "video_id"]
            .dropna()
            .unique()
        )
        daily_frames.append(
            video_ids_daily_rows(credentials, start_date, end_date, ids, content_type)
        )

    daily_df = (
        pd.concat(daily_frames, ignore_index=True)
        .groupby(["date", "content_type"], as_index=False)
        .agg(
            views=("views", "sum"),
            watch_minutes=("watch_minutes", "sum"),
            avg_view_duration_seconds=("avg_view_duration_seconds", "mean"),
        )
    )
    return complete_daily_frame(daily_df, start_date, end_date), detail_df


def format_seconds(value: float) -> str:
    minutes, seconds = divmod(int(round(value)), 60)
    return f"{minutes}:{seconds:02d}"


def kpi_frame(detail_df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        detail_df.groupby("content_type", as_index=False)
        .agg(
            views=("views", "sum"),
            videos=("video_id", "nunique"),
            watch_minutes=("watch_minutes", "sum"),
            avg_view_duration_seconds=("avg_view_duration_seconds", "mean"),
        )
        .set_index("content_type")
        .reindex(CONTENT_TYPES, fill_value=0)
        .reset_index()
    )
    grouped["avg_views"] = grouped.apply(
        lambda row: row["views"] / row["videos"] if row["videos"] else 0,
        axis=1,
    )
    grouped["watch_hours"] = grouped["watch_minutes"] / 60
    return grouped


def render_kpis(kpis: pd.DataFrame) -> None:
    columns = st.columns(4)
    for column, content_type in zip(columns, CONTENT_TYPES):
        row = kpis[kpis["content_type"] == content_type].iloc[0]
        with column:
            st.markdown(
                f"""
                <div class="kpi-card" style="border-left-color: {CONTENT_COLORS[content_type]}">
                    <div class="kpi-label">{content_type}</div>
                    <div class="kpi-value">{int(row["views"]):,}</div>
                    <div class="kpi-sub">Avg {row["avg_views"]:,.0f} views | {int(row["videos"]):,} videos</div>
                    <div class="kpi-sub">{row["watch_hours"]:,.1f} watch hours | {format_seconds(row["avg_view_duration_seconds"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def line_chart(daily_df: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(daily_df)
        .mark_line(point=True, interpolate="monotone", strokeWidth=3)
        .encode(
            x=alt.X(
                "date:T",
                title=None,
                axis=alt.Axis(
                    format="%b %d",
                    labelAngle=0,
                    labelOverlap="greedy",
                    tickCount=12,
                    grid=False,
                ),
            ),
            y=alt.Y(
                "views:Q",
                title="Views",
                axis=alt.Axis(format="~s", grid=True),
            ),
            color=alt.Color(
                "content_type:N",
                title="Content type",
                scale=alt.Scale(
                    domain=CONTENT_TYPES,
                    range=[CONTENT_COLORS[item] for item in CONTENT_TYPES],
                ),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("content_type:N", title="Content type"),
                alt.Tooltip("views:Q", title="Views", format=","),
                alt.Tooltip("watch_minutes:Q", title="Watch minutes", format=",.0f"),
                alt.Tooltip(
                    "avg_view_duration_seconds:Q",
                    title="Avg view duration sec",
                    format=",.0f",
                ),
            ],
        )
        .properties(height=440)
    )


def main() -> None:
    st.set_page_config(page_title="YouTube Content Dashboard", page_icon="YT", layout="wide")

    if "code" in st.query_params or "error" in st.query_params:
        render_youtube_reconnect_page()
        return

    page = st.sidebar.radio(
        "Go to",
        ["Dashboard", "Reconnect YouTube"],
        help="Use Reconnect YouTube only when the dashboard reports an authorization problem.",
    )
    if page == "Reconnect YouTube":
        render_youtube_reconnect_page()
        return

    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.8rem; }
        .kpi-card {
            min-height: 142px;
            padding: 18px 18px 16px;
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-left: 5px solid;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(30, 41, 59, 0.72), rgba(15, 23, 42, 0.72));
        }
        .kpi-label {
            color: #a6adb8;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .kpi-value {
            margin-top: 0.45rem;
            color: #f8fafc;
            font-size: 2rem;
            font-weight: 850;
            line-height: 1;
        }
        .kpi-sub {
            margin-top: 0.55rem;
            color: #cbd5e1;
            font-size: 0.86rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("YouTube Content Dashboard")
    st.caption("Live YouTube Analytics split by Shorts, Videos, Lives, and podcast playlist content.")

    with st.sidebar:
        st.header("Controls")
        today = date.today()
        start_date = st.date_input("Start date", value=today - timedelta(days=90))
        end_date = st.date_input("End date", value=today - timedelta(days=1))
        if st.button("Refresh data", type="primary"):
            load_dashboard_data.clear()

    if start_date > end_date:
        st.error("Start date must be on or before end date.")
        return

    try:
        with st.spinner("Fetching YouTube Analytics..."):
            daily_df, detail_df = load_dashboard_data(start_date, end_date)
    except Exception as error:
        st.error(str(error))
        st.stop()

    if daily_df.empty or detail_df.empty:
        st.warning("No YouTube Analytics data was returned for this date range.")
        return

    kpis = kpi_frame(detail_df)
    render_kpis(kpis)

    st.subheader("Views Over Time")
    st.altair_chart(line_chart(daily_df), use_container_width=True)

    st.subheader("Content Type Summary")
    summary = kpis.copy()
    summary["Avg view duration"] = summary["avg_view_duration_seconds"].map(format_seconds)
    summary = summary[
        [
            "content_type",
            "views",
            "avg_views",
            "videos",
            "watch_hours",
            "Avg view duration",
        ]
    ].rename(
        columns={
            "content_type": "Content type",
            "views": "Views",
            "avg_views": "Avg views",
            "videos": "Videos",
            "watch_hours": "Watch hours",
        }
    )
    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Content type": st.column_config.TextColumn(width="medium"),
            "Views": st.column_config.NumberColumn(format="%d", width="small"),
            "Avg views": st.column_config.NumberColumn(format="%.0f", width="small"),
            "Videos": st.column_config.NumberColumn(format="%d", width="small"),
            "Watch hours": st.column_config.NumberColumn(format="%.1f", width="small"),
            "Avg view duration": st.column_config.TextColumn(width="small"),
        },
    )

    st.subheader("Top Videos")
    top_videos = (
        detail_df.groupby(["video_id", "title", "content_type"], as_index=False)
        .agg(
            views=("views", "sum"),
            watch_minutes=("watch_minutes", "sum"),
            avg_view_duration_seconds=("avg_view_duration_seconds", "mean"),
        )
        .sort_values("views", ascending=False)
        .head(15)
    )
    top_videos["Rank"] = range(1, len(top_videos) + 1)
    top_videos["Watch hours"] = top_videos["watch_minutes"] / 60
    top_videos["Avg duration"] = top_videos["avg_view_duration_seconds"].map(format_seconds)
    top_videos = top_videos.rename(
        columns={
            "title": "Title",
            "content_type": "Type",
            "views": "Views",
        }
    )
    st.dataframe(
        top_videos[["Rank", "Title", "Views", "Type", "Watch hours", "Avg duration"]],
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", width="small"),
            "Title": st.column_config.TextColumn(width="large"),
            "Views": st.column_config.NumberColumn(format="%d", width="small"),
            "Type": st.column_config.TextColumn(width="small"),
            "Watch hours": st.column_config.NumberColumn(format="%.1f", width="small"),
            "Avg duration": st.column_config.TextColumn(width="small"),
        },
    )


if __name__ == "__main__":
    main()
