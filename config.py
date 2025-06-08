"""
Configuration settings for MTP sync service.
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
(DATA_DIR / ".execution_retry").mkdir(exist_ok=True)

# Default files
DEFAULT_EXECUTION_PLAN = DATA_DIR / "execution_plan.json"
LOG_FILE = LOG_DIR / "sync.log"

# MTP settings
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2  # For exponential backoff

# Threading settings
MAX_THREADS = 4  # For parallel checksum operations

# Checksum settings
CHECKSUM_ALGORITHM = "sha256"  # Alternative: "md5"
TEMP_DIR = Path("/tmp/mtpsync")
TEMP_DIR.mkdir(exist_ok=True)
