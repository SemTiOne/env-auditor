import os

REDIS_URL = os.environ.get("REDIS_URL")
CACHE_TTL = os.getenv("CACHE_TTL", "3600")

# Dynamic reference — cannot be statically audited
config_key = "CACHE_BACKEND"
dynamic_backend = os.environ[config_key]
