import requests
import logging
from urllib.parse import urljoin
from .configmanager import config
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def post_api(endpoint: str, payload: dict) -> bool:
    """
    Posts JSON payload to the backend API over HTTPS with basic authentication.
    Allows self-signed SSL certs.
    """
    base_url = config.get("Advanced", "BaseURL") or "https://[::1]:8000"
    full_url = urljoin(base_url, endpoint)

    username = config.get("auth", "username")
    password = config.get("auth", "password")

    try:
        response = requests.post(
            full_url,
            json=payload,
            auth=(username, password),
            verify=False,  # Accept self-signed cert
            timeout=10
        )
        if response.status_code == 200:
            logging.debug(f"✅ POST {endpoint} succeeded.")
            return True
        else:
            logging.error(f"❌ POST {endpoint} failed with {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ POST {endpoint} failed: {e}")
        return False
