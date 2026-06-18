#!/usr/bin/env python3
"""
One-time script to get a Google Calendar OAuth refresh token.
Run locally, copy the printed values into GitHub secrets:
  GCAL_CLIENT_ID
  GCAL_CLIENT_SECRET
  GCAL_REFRESH_TOKEN

Requires client_secret.json in the same directory (download from Google Cloud Console).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    'client_secret.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)
creds = flow.run_local_server(port=0)
print('GCAL_CLIENT_ID:     ', creds.client_id)
print('GCAL_CLIENT_SECRET: ', creds.client_secret)
print('GCAL_REFRESH_TOKEN: ', creds.refresh_token)
