"""Create the database schema. Run with: python -m price_intel.db.init_db"""

from price_intel.db import models  # noqa: F401  (registers models on Base.metadata)
from price_intel.db.base import Base, engine


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_schema()
    print("Schema created (or already up to date).")
