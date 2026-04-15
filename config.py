import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
LOVABLE_API_KEY = os.getenv("LOVABLE_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY", "")
