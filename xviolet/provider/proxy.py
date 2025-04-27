"""
Proxy Management for x_violet.

Handles configuration and retrieval of SOCKS5 proxy settings.
This might later incorporate rotation logic based on proxystr concepts.
"""

import os
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables from .env file
# Ensure .env is in the root directory relative to where the script is run
# Or provide a specific path: load_dotenv(dotenv_path=Path('.') / '.env')
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration --- #
# Expecting SOCKS5 proxy URL in .env, e.g., SOCKS5_PROXY=socks5h://user:pass@host:port
DEFAULT_PROXY_ENV_VAR = "SOCKS5_PROXY"

class ProxyManager:
    def __init__(self, proxy_env_var: str = DEFAULT_PROXY_ENV_VAR):
        """
        Initializes the ProxyManager, loading the proxy string from environment variables.

        Args:
            proxy_env_var: The name of the environment variable holding the proxy URL.
        """
        self._proxy_string = os.getenv(proxy_env_var)
        self._validated = False
        self._proxy_dict = None

        if self._proxy_string:
            logger.info(f"Found proxy string in env var '{proxy_env_var}'. Validating...")
            self._validate_proxy_string()
        else:
            logger.warning(
                f"Environment variable '{proxy_env_var}' not set or empty. "
                f"Proxy support disabled. Network requests will use the main connection."
            )
            # Explicitly set to None if not found or invalid
            self._proxy_string = None

    def _validate_proxy_string(self):
        """Parses and validates the proxy string."""
        # Simple validation: ensure it's a socks5 URL with netloc
        if not isinstance(self._proxy_string, str) or not self._proxy_string.strip():
            logger.error("Proxy string is empty or not a string. Proxy disabled.")
            self._proxy_string = None
            self._proxy_dict = None
            self._validated = False
            return
        try:
            # Reconstruct URL with auth: host:port:user:pass format if missing '@'
            raw = self._proxy_string
            parsed_raw = urlparse(raw)
            if parsed_raw.scheme.startswith("socks5") and "@" not in raw:
                # Expect segments: host:port:user:pass:[...]
                segs = raw.split("://", 1)[1].split(":")
                if len(segs) >= 4:
                    host, port, user, password = segs[0], segs[1], segs[2], segs[3]
                    reconstructed = f"{parsed_raw.scheme}://{user}:{password}@{host}:{port}"
                    logger.info(f"Reconstructed proxy URL with credentials: {reconstructed}")
                    self._proxy_string = reconstructed
            parsed = urlparse(self._proxy_string)
            if not parsed.scheme.startswith("socks5"):
                raise ValueError("Proxy scheme must be socks5 or socks5h")
            if not parsed.netloc:
                raise ValueError("Proxy netloc missing")
            # Accept any netloc; route all HTTP/S traffic through this proxy URL
            self._proxy_dict = {
                "http://": self._proxy_string,
                "https://": self._proxy_string,
            }
            self._validated = True
            logger.info(f"Proxy validated and configured: {self._proxy_string}")
        except Exception as e:
            logger.error(f"Invalid proxy string '{self._proxy_string}': {e}. Proxy disabled.")
            self._proxy_string = None
            self._proxy_dict = None
            self._validated = False

    @property
    def is_enabled(self) -> bool:
        """Returns True if a valid proxy is configured and enabled."""
        return self._validated and self._proxy_string is not None

    def get_proxy_url(self) -> str | None:
        """
        Returns the raw proxy URL string (e.g., 'socks5h://user:pass@host:port')
        if the proxy is enabled, otherwise None.
        """
        return self._proxy_string if self.is_enabled else None

    def get_proxy_dict_for_requests(self) -> dict[str, str] | None:
        """
        Returns a dictionary suitable for use with the 'requests' library
        (e.g., {'http': 'socks5h://...', 'https': 'socks5h://...'})
        if the proxy is enabled, otherwise None.

        Note: 'requests' uses 'http' and 'https' keys.
        """
        if not self.is_enabled:
            return None
        return {
            "http": self._proxy_string,
            "https": self._proxy_string,
        }

    def get_proxy_dict_for_httpx(self) -> dict[str, str] | None:
        """
        Returns a dictionary suitable for use with the 'httpx' library
        (e.g., {'http://': 'socks5h://...', 'https://': 'socks5h://...'})
        if the proxy is enabled, otherwise None.

        Note: 'httpx' uses 'http://' and 'https://' keys.
        """
        return self._proxy_dict if self.is_enabled else None


# --- Global Instance (optional, for convenience) ---
# You can either instantiate ProxyManager where needed or use this global instance.
# Consider dependency injection for better testability in larger applications.
proxy_manager = ProxyManager()

# --- Example Usage --- #
if __name__ == "__main__":
    print("--- Proxy Manager Test --- ")
    print(f"Attempting to load proxy from env var: {DEFAULT_PROXY_ENV_VAR}")

    # Use the global instance or create a new one
    manager = proxy_manager # or manager = ProxyManager()

    if manager.is_enabled:
        print("\nProxy is enabled.")
        print(f"  Raw URL: {manager.get_proxy_url()}")
        print(f"  Requests Dict: {manager.get_proxy_dict_for_requests()}")
        print(f"  HTTPX Dict: {manager.get_proxy_dict_for_httpx()}")

        # Example with requests (requires 'pip install requests[socks]')
        try:
            import requests
            print("\nTesting proxy with 'requests' library (to httpbin.org/ip)...")
            proxies_req = manager.get_proxy_dict_for_requests()
            if proxies_req:
                response = requests.get("https://httpbin.org/ip", proxies=proxies_req, timeout=15)
                response.raise_for_status() # Raise an exception for bad status codes
                print(f"  Success! Response (requests): {response.json()}")
            else:
                 print("  Skipping requests test: Proxy dictionary is None.")
        except ImportError:
            print("  'requests' library not found. Skipping requests test.")
            print("  Install with: pip install requests[socks]")
        except requests.exceptions.RequestException as e:
            print(f"  Requests test failed: {e}")
        except Exception as e:
            print(f"  An unexpected error occurred during requests test: {e}")

        # Example with httpx (requires 'pip install httpx[socks]')
        try:
            import httpx
            print("\nTesting proxy with 'httpx' library (to httpbin.org/ip)...")
            proxies_httpx = manager.get_proxy_dict_for_httpx()
            if proxies_httpx:
                 # httpx with SOCKS support ('pip install httpx[socks]') should handle
                 # the socks5h scheme directly when passed via the 'proxies' argument.
                with httpx.Client(proxies=proxies_httpx, timeout=15) as client:
                    response = client.get("https://httpbin.org/ip")
                    response.raise_for_status()
                    print(f"  Success! Response (httpx): {response.json()}")
            else:
                 print("  Skipping httpx test: Proxy dictionary is None.")
        except ImportError:
            print("  'httpx' library not found or 'httpx[socks]' is not installed. Skipping httpx test.")
            print("  Install with: pip install httpx[socks]")
        except httpx.RequestError as e:
            print(f"  HTTPX test failed: {e}")
        except Exception as e:
            print(f"  An unexpected error occurred during httpx test: {e}")

    else:
        print("\nProxy is disabled or not configured correctly.")
        print(f"  Ensure the {DEFAULT_PROXY_ENV_VAR} environment variable is set correctly in your .env file.")
        print("  Example: SOCKS5_PROXY=socks5h://user:pass@your_proxy_host:1080")
        print("  (Make sure the .env file is in the root of the project or detectable by python-dotenv)")
