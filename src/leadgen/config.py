"""Loads the Google Maps Platform API key from the environment.

Get a key at https://console.cloud.google.com/google/maps-apis/credentials
with the "Places API (New)" enabled. Set it as an environment variable
(never on the command line, never committed):

    export GOOGLE_MAPS_API_KEY=...

or drop it in a `.env` file at the repo root (gitignored):

    GOOGLE_MAPS_API_KEY=...
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

API_KEY_ENV_VAR = "GOOGLE_MAPS_API_KEY"


def get_api_key() -> str:
    key = os.environ.get(API_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{API_KEY_ENV_VAR} is not set. Get a key at "
            "https://console.cloud.google.com/google/maps-apis/credentials "
            "(enable 'Places API (New)'), then export it or add it to a .env file."
        )
    return key
