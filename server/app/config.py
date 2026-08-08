import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


_load_env_file(Path(__file__).resolve().parents[1] / ".env")

API_TOKEN = os.environ.get("PHONE_LOCATOR_API_TOKEN", "").strip()
BIND_HOST = os.environ.get("PHONE_LOCATOR_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("PHONE_LOCATOR_BIND_PORT", "8003"))
DATABASE_PATH = Path(
    os.environ.get(
        "PHONE_LOCATOR_DATABASE_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "phone-locator.db"),
    )
)
NOMINATIM_BASE_URL = os.environ.get(
    "PHONE_LOCATOR_NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
).rstrip("/")
NOMINATIM_USER_AGENT = os.environ.get(
    "PHONE_LOCATOR_NOMINATIM_USER_AGENT",
    "PhoneLocator/1.0 (personal; https://github.com/kklasmeier/andriod-PhoneLocator)",
)
NOMINATIM_MIN_INTERVAL_SEC = float(os.environ.get("PHONE_LOCATOR_NOMINATIM_MIN_INTERVAL_SEC", "1.1"))
