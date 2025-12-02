"""
fetchr configuration module - Independent configuration for the download library
"""
import os
from pathlib import Path
from dotenv import load_dotenv

def get_root_dir() -> Path:
    """Get root directory - /content in Colab, home() otherwise."""
    if os.path.exists("/content") or "COLAB_GPU" in os.environ:
        return Path("/content")
    return Path.home()

ROOT_DIR = get_root_dir()
CONFIG_DIR = ROOT_DIR / ".config" / "fetchr"

def get_env_path() -> Path:
    env_path = CONFIG_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    return env_path

# Load environment
load_dotenv(get_env_path())

def get_env_or_default(key: str, default: str) -> str:
    """Get environment variable or return default, handling empty strings."""
    value = os.getenv(key)
    return value if value else default

# Directories
CAPTCHAS_DIR = get_env_or_default("FETCHR_CAPTCHAS_DIR", str(ROOT_DIR / ".cache" / "fetchr" / "captchas"))
DOWNLOAD_DIR = get_env_or_default("FETCHR_DOWNLOAD_DIR", str(ROOT_DIR / ".cache" / "fetchr" / "downloads"))

# Create directories
try:
    os.makedirs(CAPTCHAS_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
except Exception:
    pass

# Proxies
PROXIES_PATH = Path(get_env_or_default("FETCHR_PROXIES_PATH", str(CONFIG_DIR / "proxies.txt")))

# Service tokens
DEBRID_GATEWAY = os.getenv("FETCHR_DEBRID_GATEWAY") or os.getenv("DEBRID_GATEWAY")
REALDEBRID_BEARER_TOKEN = os.getenv("FETCHR_REALDEBRID_TOKEN") or os.getenv("REALDEBRID_BEARER_TOKEN")

# Tor settings
TOR_PORT = int(os.getenv("FETCHR_TOR_PORT", "9050"))
