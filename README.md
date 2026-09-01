# YouTube Content Dashboard

This Streamlit app shows YouTube performance by content type: Shorts, Videos, Live streams, and Podcasts.

It is intended for a non-technical team to open in a browser, choose a date range, and review the latest performance without running reports manually.

## What The Dashboard Shows

- KPI cards for each content type
- Views over time by content type
- A summary table with views, average views, video count, watch hours, and average view duration
- A top videos table showing the strongest individual videos in the selected date range

## Where The App Lives

- GitHub repo: `myschne/VideoDash`
- Streamlit app file: `app.py`
- Streamlit Cloud main file path: `app.py`

## Day-To-Day Use

1. Open the Streamlit dashboard.
2. In the left menu, choose **Dashboard**.
3. Pick a start date and end date.
4. Review the KPI cards, trend chart, summary table, and top videos table.
5. Use **Refresh data** if you need the app to pull fresh YouTube data.

The dashboard reads live data from YouTube. If YouTube has not finished processing very recent activity, the most recent day may change later.

## What Each Content Type Means

- **Shorts**: videos that are 60 seconds or shorter, excluding podcasts and live streams
- **Videos**: regular non-live YouTube videos
- **Lives**: videos with YouTube live-stream metadata
- **Podcasts**: videos found in the configured podcast playlist

Podcast videos are counted as Podcasts first so they are not double-counted as regular Videos.

## Streamlit Secrets

The dashboard needs YouTube credentials stored in Streamlit Cloud Secrets. Do not put real credentials in GitHub.

In Streamlit Cloud:

1. Open the app.
2. Choose **Manage app**.
3. Open **Settings**.
4. Open **Secrets**.
5. Add or update the blocks below.

```toml
youtube_redirect_uri = "https://videodash.streamlit.app/"

[youtube]
podcast_playlist_id = "PLEMmsgg0GMzCJZnBjaIyMBUPVx9hT0Ft0"

[youtube_web_oauth_client]
client_id = "YOUR_GOOGLE_OAUTH_CLIENT_ID.apps.googleusercontent.com"
project_id = "YOUR_GOOGLE_CLOUD_PROJECT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_secret = "YOUR_GOOGLE_OAUTH_CLIENT_SECRET"
redirect_uris = ["https://videodash.streamlit.app/"]

[youtube_oauth_token]
token = "OPTIONAL_ACCESS_TOKEN_FROM_RECONNECT_FLOW"
refresh_token = "YOUR_YOUTUBE_REFRESH_TOKEN"
token_uri = "https://oauth2.googleapis.com/token"
client_id = "YOUR_GOOGLE_OAUTH_CLIENT_ID.apps.googleusercontent.com"
client_secret = "YOUR_GOOGLE_OAUTH_CLIENT_SECRET"
scopes = [
  "https://www.googleapis.com/auth/youtube.readonly",
  "https://www.googleapis.com/auth/yt-analytics.readonly"
]
```

After changing Secrets, save the page and wait for Streamlit to restart the app.

## Reconnect YouTube

Use this when the dashboard says YouTube authorization expired or was revoked.

1. Open the dashboard.
2. In the left menu, choose **Reconnect YouTube**.
3. Select **Start YouTube sign-in**.
4. Select **Continue to Google**.
5. Sign in with the Google account that owns or manages the YouTube channel.
6. Approve the requested YouTube read-only permissions.
7. When Google returns to Streamlit, copy the generated `[youtube_oauth_token]` block.
8. In Streamlit Cloud, open **Manage app**, then **Settings**, then **Secrets**.
9. Replace the old `[youtube_oauth_token]` section with the new block.
10. Save, wait for the app to restart, and return to **Dashboard**.

Streamlit does not allow the app to rewrite its own saved Secrets, so the copy-and-save step is required.

## One-Time Google Setup

The Google OAuth client must be a **Web application** client.

In Google Cloud Console, the OAuth client needs:

- YouTube Data API v3 enabled
- YouTube Analytics API enabled
- Authorized redirect URI matching `youtube_redirect_uri`
- Access to the YouTube channel through the Google account used during reconnect

Required scopes:

```text
https://www.googleapis.com/auth/youtube.readonly
https://www.googleapis.com/auth/yt-analytics.readonly
```

## Local Use

Most users should use the hosted Streamlit app. A technical administrator can run the app locally with:

```powershell
python -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
python -m streamlit run app.py
```

Before running locally, fill `.streamlit/secrets.toml` with real values. That file is ignored by Git and should not be committed.

## Maintenance Checklist

- Keep the Google account used for YouTube authorization active.
- Refresh the YouTube token if the dashboard reports an authorization problem.
- Keep the Streamlit app private if the YouTube data should not be public.
- Do not commit `.streamlit/secrets.toml` or any real tokens to GitHub.
- If the podcast playlist changes, update `podcast_playlist_id` in Streamlit Secrets.

## Troubleshooting

If the dashboard shows an authorization error, use **Reconnect YouTube**.

If the dashboard shows no data for the selected dates, try a wider date range and confirm YouTube has processed analytics for that period.

If the Streamlit app fails immediately after a Secrets change, check for missing quotation marks, missing brackets, or duplicated TOML section names in Secrets.
