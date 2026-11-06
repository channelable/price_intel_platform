"""Start (or reuse) the local dev Postgres and print its URL.

Dev-only fallback for machines without Docker. It uses the Postgres binaries
bundled with the ``pgserver`` package, but calls ``pg_ctl`` directly: pgserver
keeps its log inside the data directory, which can hit a Windows file-lock on
restart. A separate log and a fixed port make this repeatable.

    .venv\\Scripts\\python.exe scripts\\dev_db.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pgserver
import psutil

HOST = "127.0.0.1"
PORT = 55432
DB_USER = "postgres"
DATABASE = "postgres"

ROOT = Path(__file__).resolve().parent.parent
PGDATA = ROOT / "data" / "pgdata"
LOG = ROOT / "data" / "pg.log"
BIN = Path(pgserver.__file__).parent / "pginstall" / "bin"
EXE = ".exe" if os.name == "nt" else ""


def database_url() -> str:
    return f"postgresql://{DB_USER}:@{HOST}:{PORT}/{DATABASE}"


def is_running() -> bool:
    import psycopg

    try:
        with psycopg.connect(database_url(), connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def clear_stale_pid() -> None:
    """A crash or reboot leaves postmaster.pid behind; pg_ctl refuses to start."""
    pid_file = PGDATA / "postmaster.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
    except (IndexError, ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return
    if not psutil.pid_exists(pid):
        pid_file.unlink(missing_ok=True)


def main() -> None:
    PGDATA.parent.mkdir(parents=True, exist_ok=True)

    if not (PGDATA / "PG_VERSION").exists():
        subprocess.run(
            [
                str(BIN / f"initdb{EXE}"),
                "--auth=trust",
                "--auth-local=trust",
                "--encoding=utf8",
                "-U",
                DB_USER,
                "-D",
                str(PGDATA),
            ],
            check=True,
        )

    if not is_running():
        clear_stale_pid()
        subprocess.run(
            [
                str(BIN / f"pg_ctl{EXE}"),
                "-D",
                str(PGDATA),
                "-w",
                "-t",
                "60",
                "-o",
                f"-h {HOST} -p {PORT}",
                "-l",
                str(LOG),
                "start",
            ],
            check=True,
        )

    print(database_url())


if __name__ == "__main__":
    main()
