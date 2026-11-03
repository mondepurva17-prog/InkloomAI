import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DB_PATH = Path(__file__).with_name("inkloom.db")


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT NOT NULL,
            score INTEGER NOT NULL,
            findings TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(review_id) REFERENCES reviews(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS guidelines (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            brand_name TEXT NOT NULL,
            tone TEXT NOT NULL,
            approved_terms TEXT NOT NULL,
            forbidden_terms TEXT NOT NULL,
            required_terms TEXT NOT NULL
        );
        """)

        demo_users = [
            ("Demo Admin", "admin@inkloom.demo",
             "Admin@123", "admin"),
            ("Demo Reviewer", "reviewer@inkloom.demo",
             "Review@123", "reviewer"),
            ("Demo Creator", "creator@inkloom.demo",
             "Create@123", "creator")
        ]

        for name, email, password, role in demo_users:
            existing = db.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()

            if not existing:
                db.execute("""
                    INSERT INTO users(name, email, password, role)
                    VALUES (?, ?, ?, ?)
                """, (
                    name,
                    email,
                    generate_password_hash(password),
                    role
                ))

        db.execute("""
            INSERT OR IGNORE INTO guidelines
            (id, brand_name, tone, approved_terms,
             forbidden_terms, required_terms)
            VALUES (1, 'Inkloom AI',
            'Clear, helpful, confident and trustworthy',
            'simple,reliable,thoughtful',
            'guaranteed,risk-free,100% cure',
            '')
        """)