import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/campuswatt.db")

APP_TITLE = "CampusWatt - Campus Energy Load Forecasting & Peak Reduction System"
APP_VERSION = "1.0.0"

# Default CampusWatt settings
DEFAULT_SETTINGS = {
    "campusName": "Riverview Technical College",
    "location": "Riverview",
    "currency": "$",
    "rate": 0.118,
    "demandRate": 14.5,
    "peakThreshold": 450.0,
    "evCharging": True,
    "evKw": 22.0,
    "userName": "A. Jordan",
    "role": "Energy Manager",
    "theme": "light",
    "reduceMotion": False,
}
