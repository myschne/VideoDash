# VideoDash

Streamlit dashboard for YouTube content performance by content type: Shorts, Videos, Lives, and Podcasts.

## Run Locally

```powershell
python -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
python -m streamlit run app.py
```

Fill `.streamlit/secrets.toml` with the YouTube OAuth values before running locally.

## Streamlit Cloud

Deploy this repo with:

- Repository: `myschne/VideoDash`
- Branch: `main`
- Main file path: `app.py`

Add these secrets in Streamlit Cloud app settings:

```toml
[youtube]
client_id = "YOUR_GOOGLE_OAUTH_CLIENT_ID"
client_secret = "YOUR_GOOGLE_OAUTH_CLIENT_SECRET"
refresh_token = "YOUR_YOUTUBE_REFRESH_TOKEN"
token_uri = "https://oauth2.googleapis.com/token"
podcast_playlist_id = "PLEMmsgg0GMzCJZnBjaIyMBUPVx9hT0Ft0"
```

The OAuth client needs these scopes:

```text
https://www.googleapis.com/auth/youtube.readonly
https://www.googleapis.com/auth/yt-analytics.readonly
```
