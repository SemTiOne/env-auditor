import os

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))


def get_connection():
    url = os.environ["DATABASE_URL"]
    return url
