import os

from dotenv import load_dotenv
from supabase import create_client, Client


# Load .env
load_dotenv()


# Read credentials
SUPABASE_URL = os.getenv(
    "SUPABASE_URL"
)

SUPABASE_SECRET_KEY = os.getenv(
    "SUPABASE_SECRET_KEY"
)


# Validate credentials
if not SUPABASE_URL:
    raise ValueError(
        "SUPABASE_URL is missing from .env"
    )


if not SUPABASE_SECRET_KEY:
    raise ValueError(
        "SUPABASE_SECRET_KEY is missing from .env"
    )


# Create Supabase client
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)