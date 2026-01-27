import os
import sys
import base64
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("EnexCommon")

def load_config():
    """
    Load environment variables from .env file using absolute paths.
    """
    # .../scripts/common.py -> .../scripts -> .../Enex_Antigravity
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    env_path = os.path.join(project_root, ".env")
    
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    else:
        # Fallback to CWD logic if needed, or warn
        if os.path.exists(".env"):
            load_dotenv(".env")
        else:
            logger.warning(f".env not found at {env_path}")

    # Verify critical keys
    required_keys = ["ORKA_USER", "ORKA_PASSWORD"]
    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")
    else:
        logger.debug("Environment variables loaded successfully.")

def get_orka_credentials():
    """
    Retrieve and encode ORKA credentials from environment.
    Returns (encoded_user, encoded_password) or (None, None).
    """
    username = os.getenv("ORKA_USER")
    password = os.getenv("ORKA_PASSWORD")
    
    if not username or not password:
        logger.error("ORKA_USER or ORKA_PASSWORD not found in environment.")
        return None, None
        
    encoded_user = base64.b64encode(username.encode()).decode()
    encoded_password = base64.b64encode(password.encode()).decode()
    return encoded_user, encoded_password

def get_orka_token():
    """
    Authenticate with Orka Manager and return access token.
    """
    login_url = "https://www.orkamanager.com/orkapi/login"
    encoded_user, encoded_password = get_orka_credentials()
    
    if not encoded_user:
        return None
        
    payload = {
        "user": encoded_user,
        "password": encoded_password
    }
    
    try:
        # Orka requires standard form data or json? The original scripts used data=payload (form-urlencoded)
        # but one script manually set a dict. Let's stick to requests default which is form-urlencoded when data is dict.
        response = requests.post(login_url, data=payload, timeout=15)
        response.raise_for_status()
        
        token = response.json().get("access_token")
        if token:
            logger.info("Orka authentication successful.")
            return token
        else:
            logger.error("Token not found in login response.")
            return None
    except Exception as e:
        logger.error(f"Error during Orka login: {e}")
        return None

def get_supabase_client():
    """
    Initialize and return Supabase client.
    """
    from supabase import create_client, Client
    
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    
    if not url or not key:
        logger.error("SUPABASE_URL or SUPABASE_KEY not found in environment.")
        return None
        
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None

def clean_float(value):
    """
    Convert string with commas to float safely.
    """
    if isinstance(value, str):
        value = value.replace('.', '').replace(',', '.').strip() # Remove thousands separator dot? 
        # Wait, if 1.000,00 is the format:
        # replace('.', '') -> 1000,00
        # replace(',', '.') -> 1000.00 -> Float works.
        # BUT if format is just 1,000.50 (US), this breaks.
        # Assuming Spanish locale from context (comma decimal).
        pass 
        
    try:
        # Handle the logic cleanly
        if isinstance(value, str):
            # Simple approach: assume standard Spanish format (1.234,56)
            # 1. Remove dots (thousands)
            # 2. Replace comma with dot
            clean_s = value.replace('.', '').replace(',', '.')
            return float(clean_s)
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def get_downloads_dir():
    """
    Return the path to the user's Downloads directory.
    """
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "/tmp"
    return os.path.join(os.path.expanduser("~"), "Downloads")

def trigger_download_via_stdout(file_path):
    """
    Reads a file and prints a magic string to stdout that the frontend
    will intercept to trigger a file download.
    Format: __FILE_DOWNLOAD__;;filename;;mimetype;;base64_data
    """
    if not os.path.exists(file_path):
        logger.error(f"Cannot trigger download: File not found {file_path}")
        return

    try:
        filename = os.path.basename(file_path)
        # Determine mime type roughly
        mime = "application/octet-stream"
        if filename.endswith(".csv"): mime = "text/csv"
        elif filename.endswith(".xlsx"): mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif filename.endswith(".json"): mime = "application/json"
        
        with open(file_path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode('utf-8')
            
        print(f"__FILE_DOWNLOAD__;;{filename};;{mime};;{b64}")
        logger.info(f"Triggered frontend download for {filename}")
        
    except Exception as e:
        logger.error(f"Error triggering download: {e}")
