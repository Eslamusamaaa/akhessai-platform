"""Create a user (e.g. the first specialist/admin) directly in the database.

Run locally; nothing is stored on disk and the password is never echoed:

    pip install sqlalchemy psycopg2-binary "passlib[argon2]" argon2-cffi
    python backend/scripts/create_user.py

You will be prompted for the database URL, username, role and password.
"""
import getpass
import sys
import uuid
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

ROLES = {"parent", "teacher", "specialist", "admin"}


def main() -> None:
    db_url = getpass.getpass("DATABASE_URL (hidden): ").strip()
    username = input("Username: ").strip()
    role = input(f"Role {sorted(ROLES)}: ").strip()
    password = getpass.getpass("Password (12+ chars, hidden): ")
    if role not in ROLES or len(username) < 3 or len(password) < 12:
        sys.exit("Invalid input: check the role, username (3+) and password (12+).")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")

    pw_hash = CryptContext(schemes=["argon2"]).hash(password)
    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}).first():
            sys.exit("That username already exists.")
        conn.execute(
            text(
                "INSERT INTO users (id, username, password_hash, role, created_at) "
                "VALUES (:id, :u, :h, :r, :c)"
            ),
            {"id": str(uuid.uuid4()), "u": username, "h": pw_hash, "r": role, "c": datetime.utcnow()},
        )
    print(f"Created {role} user '{username}'.")


if __name__ == "__main__":
    main()
