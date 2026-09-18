"""
Run once, against the real database, to populate the users table.

    python seed_users.py

Uses db.connect() directly rather than a hardcoded path, so this works the
same locally and inside the container, wherever DB_PATH actually points.

Never commit real passwords to the repo. Run this, confirm the logins work,
then delete or blank out the USERS dict below before pushing — treat this
file's content as disposable, not a permanent record.
"""
import hashlib
import secrets

import db

# username -> (plaintext password, role)
USERS = {
    "RyanL":    ("pencilgarden",   "editor"),
    "RyanB":    ("islandvelvet",   "editor"),
    "ChrisS":   ("coffeecanyon",   "editor"),
    "JohnS":    ("windowwillow",   "editor"),
    "BrettH":   ("riverwindow",    "editor"),
    "AdamD":    ("maplegarden",    "editor"),
    "MikeB":    ("pencilriver",    "editor"),
    "JasonJ":   ("tableharbor",    "editor"),
    "NathanVW": ("mapletable",     "editor"),
    "ZoeT":     ("islandriver",    "editor"),
    "viewer":   ("viewer",         "viewer"),
}


def hash_password(password: str) -> str:
    # Matches auth.hash_password() exactly — must stay in sync, since this
    # writes hashes that auth.py's _verify() has to be able to read back.
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def main():
    db.init()  # make sure the users table exists (schema.sql includes it)
    conn = db.connect()
    try:
        for username, (password, role) in USERS.items():
            conn.execute(
                "INSERT OR REPLACE INTO users (username, password_hash, role) "
                "VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
        conn.commit()
    finally:
        conn.close()
    print(f"Seeded {len(USERS)} users.")


if __name__ == "__main__":
    main()
