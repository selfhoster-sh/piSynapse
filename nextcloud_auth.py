#!/usr/bin/env python3
"""
piSynapse Nextcloud Auth
Provides a CalDAV client instance configured from environment variables.
"""

import os
import caldav
from dotenv import load_dotenv

load_dotenv()

NEXTCLOUD_URL      = os.getenv("NEXTCLOUD_URL")
NEXTCLOUD_USER     = os.getenv("NEXTCLOUD_USER")
NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD")


def get_nextcloud_client():
    """Returns a CalDAV client for the configured Nextcloud instance,
    or None if credentials are missing."""
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None

    # CalDAV endpoint is always at /remote.php/dav/ in Nextcloud
    caldav_url = f"{NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/"

    client = caldav.DAVClient(
        url=caldav_url,
        username=NEXTCLOUD_USER,
        password=NEXTCLOUD_PASSWORD,
    )
    return client
