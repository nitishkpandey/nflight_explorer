from pathlib import Path
from dotenv import load_dotenv
import os


BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Expose the API key as a constant
#AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY")


if not AIRLABS_API_KEY:
    # Helpful message if something is wrong
    raise RuntimeError(
        "AIRLABS_API_KEY is not set. "
        "Check your .env file in the project root."
    )