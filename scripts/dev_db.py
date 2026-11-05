"""Start (or reuse) the local dev Postgres and print its URL.

Dev-only fallback for machines without Docker. The server keeps running after
this script exits, so later commands can connect to it. Data lives in data/pgdata.

    .venv\\Scripts\\python.exe scripts\\dev_db.py
"""

from pathlib import Path

import pgserver

PGDATA = Path(__file__).resolve().parent.parent / "data" / "pgdata"


def main() -> None:
    PGDATA.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(PGDATA, cleanup_mode=None)
    print(server.get_uri())


if __name__ == "__main__":
    main()
