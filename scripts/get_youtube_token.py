#!/usr/bin/env python3
"""
scripts/get_youtube_token.py — One-time OAuth2 token generator for YouTube.

Run this script ONCE on your local machine to get a refresh token.
Then add the printed values as GitHub Secrets.

Prerequisites:
  1. Go to https://console.cloud.google.com/
  2. Create a project and enable "YouTube Data API v3"
  3. Go to APIs & Services → Credentials → Create OAuth 2.0 Client ID
     - Application type: Desktop App
     - Download the JSON → copy client_id and client_secret into your .env

Usage:
  python scripts/get_youtube_token.py

What it does:
  - Opens a browser window for you to log in with your Google/YouTube account
  - Prints your YOUTUBE_REFRESH_TOKEN to the terminal
  - Copy that token into .env and into your GitHub Secret: YOUTUBE_REFRESH_TOKEN
"""

import os
import sys

# Add project root to path so we can import dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main() -> None:
    client_id     = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n❌  YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env\n")
        print("  Steps:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Enable YouTube Data API v3")
        print("  3. Create OAuth 2.0 Client ID (Desktop App)")
        print("  4. Copy client_id and client_secret into your .env\n")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id":                  client_id,
            "client_secret":              client_secret,
            "redirect_uris":              ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri":                   "https://accounts.google.com/o/oauth2/auth",
            "token_uri":                  "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs",
        }
    }

    print("\n🔑  Starting YouTube OAuth2 flow...")
    print("   A browser window will open. Log in with your YouTube channel account.\n")

    flow = InstalledAppFlow.from_client_config(client_config, scopes=_SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\n✅  Authorization successful!\n")
    print("=" * 60)
    print("  Add these to your .env and GitHub Secrets:")
    print("=" * 60)
    print(f"\n  YOUTUBE_CLIENT_ID     = {client_id}")
    print(f"  YOUTUBE_CLIENT_SECRET = {client_secret}")
    print(f"  YOUTUBE_REFRESH_TOKEN = {credentials.refresh_token}")
    print("\n" + "=" * 60)
    print("\n⚠️  Keep these values secret — never commit them to Git.\n")


if __name__ == "__main__":
    main()
