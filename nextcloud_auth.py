import os
import caldav
from dotenv import load_dotenv

load_dotenv()

NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER")
NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD")

def get_nextcloud_client():
    """Nextcloud CalDAV client."""
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None
        
    caldav_url = f"{NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/"
    
    client = caldav.DAVClient(
        url=caldav_url,
        username=NEXTCLOUD_USER,
        password=NEXTCLOUD_PASSWORD
    )
    return client
