# YoAgent — Deployment Guide (GitHub Actions)

Deploy YoAgent to run automatically twice daily for free using GitHub Actions.

---

## Step 1 — Fork / Push the Repo

Push this project to a GitHub repository. The workflow file at
`.github/workflows/repost.yml` will be picked up automatically.

---

## Step 2 — Get Your Instagram Session ID

1. Log into Instagram in your browser (Chrome recommended).
2. Open DevTools → **Application** → **Cookies** → `https://www.instagram.com`
3. Find the cookie named `sessionid` and copy its value.

---

## Step 3 — Set Up YouTube OAuth2 (One-Time Local Step)

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project → Enable **YouTube Data API v3**.
3. Go to **APIs & Services → Credentials → Create OAuth 2.0 Client ID**
   - Application type: **Desktop App**
   - Note down the **Client ID** and **Client Secret**.
4. Add them to your local `.env`:
   ```
   YOUTUBE_CLIENT_ID=...
   YOUTUBE_CLIENT_SECRET=...
   ```
5. Run the token helper:
   ```bash
   python scripts/get_youtube_token.py
   ```
6. A browser will open — log in with your **YouTube channel account**.
7. Copy the printed `YOUTUBE_REFRESH_TOKEN`.

---

## Step 4 — Add GitHub Secrets

Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these 5 secrets:

| Secret Name | Value |
|---|---|
| `IG_SCRAPE_USER` | Your Instagram username |
| `IG_SESSION_ID` | The `sessionid` cookie value from Step 2 |
| `YOUTUBE_CLIENT_ID` | From Google Cloud Console |
| `YOUTUBE_CLIENT_SECRET` | From Google Cloud Console |
| `YOUTUBE_REFRESH_TOKEN` | From `get_youtube_token.py` output |

---

## Step 5 — Test Manually

Go to your repo → **Actions → YouTube Shorts Pipeline → Run workflow**

Check the logs to confirm:
- ✅ Reel scraped from `@softeningsayings`
- ✅ YouTube title / description generated
- ✅ Video uploaded to YouTube Shorts
- ✅ `data/reposted_ids.txt` committed back

---

## Schedule

The pipeline runs automatically at:
- **6:00 AM IST** (12:30 AM UTC)
- **6:00 PM IST** (12:30 PM UTC)

To change the schedule, edit the `cron` value in `.github/workflows/repost.yml`.

---

## Refreshing the Instagram Session

Instagram session cookies expire periodically (~90 days).  
When the pipeline starts failing with auth errors, repeat Step 2 and update the `IG_SESSION_ID` secret.
