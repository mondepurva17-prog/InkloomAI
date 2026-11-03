
import os
import re
import json
import sqlite3
import logging
import traceback

from pathlib import Path
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException


# =========================================================
# APPLICATION CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "inkloom.db"

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "inkloom-development-secret-change-this"
)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

MAX_ANALYSIS_LENGTH = 20000

logging.basicConfig(level=logging.INFO)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


# =========================================================
# DEFAULT BRAND GUIDELINES
# =========================================================

def default_guidelines():
    return {
        "brand_name": "Inkloom AI",
        "tone": "Clear, helpful, confident, trustworthy",
        "approved_terms": [
            "simple",
            "reliable",
            "thoughtful"
        ],
        "forbidden_terms": [
            "guaranteed",
            "risk-free",
            "100% cure"
        ],
        "required_terms": []
    }


# =========================================================
# DATABASE INITIALIZATION AND MIGRATION
# =========================================================

def init_db():

    with get_db() as conn:

        # USERS TABLE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'reviewer',
                created_at TEXT
            )
        """)

        # FIX OLD DATABASE COLUMNS
        columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        ]

        if "created_at" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN created_at TEXT"
            )

        if "role" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'reviewer'"
            )

        # GUIDELINES TABLE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guidelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_name TEXT,
                tone TEXT,
                approved_terms TEXT,
                forbidden_terms TEXT,
                required_terms TEXT,
                updated_at TEXT
            )
        """)

        # REVIEWS TABLE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                score INTEGER,
                status TEXT DEFAULT 'pending',
                findings TEXT,
                analysis_type TEXT,
                reviewer TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # AUDIT LOGS TABLE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                details TEXT,
                user_email TEXT,
                created_at TEXT
            )
        """)

        # CHECK GUIDELINES
        existing = conn.execute(
            "SELECT id FROM guidelines LIMIT 1"
        ).fetchone()

        if not existing:
            defaults = default_guidelines()

            conn.execute("""
                INSERT INTO guidelines (
                    brand_name,
                    tone,
                    approved_terms,
                    forbidden_terms,
                    required_terms,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                defaults["brand_name"],
                defaults["tone"],
                json.dumps(defaults["approved_terms"]),
                json.dumps(defaults["forbidden_terms"]),
                json.dumps(defaults["required_terms"]),
                now_iso()
            ))

        # DEMO USERS
        demo_users = [
            (
                "Admin",
                "admin@inkloom.ai",
                "admin123",
                "admin"
            ),
            (
                "Reviewer",
                "reviewer@inkloom.ai",
                "reviewer123",
                "reviewer"
            )
        ]

        for name, email, password, role in demo_users:

            user = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            ).fetchone()

            if not user:
                conn.execute("""
                    INSERT INTO users (
                        name,
                        email,
                        password,
                        role,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name,
                    email,
                    generate_password_hash(password),
                    role,
                    now_iso()
                ))


# =========================================================
# GUIDELINES FUNCTIONS
# =========================================================

def get_guidelines():

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM guidelines ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        return default_guidelines()

    return {
        "brand_name": row["brand_name"] or "Inkloom AI",
        "tone": row["tone"] or "",
        "approved_terms": json.loads(
            row["approved_terms"] or "[]"
        ),
        "forbidden_terms": json.loads(
            row["forbidden_terms"] or "[]"
        ),
        "required_terms": json.loads(
            row["required_terms"] or "[]"
        )
    }


def normalize_terms(value):

    if isinstance(value, str):
        return [
            term.strip()
            for term in value.split(",")
            if term.strip()
        ]

    if isinstance(value, list):
        return [
            str(term).strip()
            for term in value
            if str(term).strip()
        ]

    return []


# =========================================================
# AUTHENTICATION
# =========================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("user"):
            return jsonify({
                "error": "Please login first."
            }), 401

        return function(*args, **kwargs)

    return wrapper


def reviewer_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("user"):
            return jsonify({
                "error": "Please login first."
            }), 401

        if session.get("role") not in ["admin", "reviewer"]:
            return jsonify({
                "error": "Reviewer permission required."
            }), 403

        return function(*args, **kwargs)

    return wrapper


def add_audit_log(action, details=""):

    with get_db() as conn:
        conn.execute("""
            INSERT INTO audit_logs (
                action,
                details,
                user_email,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            action,
            details,
            session.get("user", "system"),
            now_iso()
        ))


# =========================================================
# CONTENT ANALYSIS ENGINE
# =========================================================

def analyse_content(content):

    guidelines = get_guidelines()

    findings = []
    score = 100
    text = content.lower()

    def add_finding(level, message, matched_text=None):

        nonlocal score

        deductions = {
            "high": 25,
            "medium": 15,
            "low": 7,
            "notice": 3
        }

        score -= deductions.get(level, 0)

        findings.append({
            "severity": level,
            "message": message,
            "matched_text": matched_text
        })

    # FORBIDDEN TERMS
    for term in guidelines["forbidden_terms"]:

        pattern = r"\b" + re.escape(term.lower()) + r"\b"

        if re.search(pattern, text):
            add_finding(
                "high",
                "Restricted brand term found.",
                term
            )

    # REQUIRED TERMS
    for term in guidelines["required_terms"]:

        if term.lower() not in text:
            add_finding(
                "medium",
                "Required brand phrase is missing.",
                term
            )

    # APPROVED TERMS
    for term in guidelines["approved_terms"]:

        if term.lower() in text:
            findings.append({
                "severity": "notice",
                "message": "Approved brand language detected.",
                "matched_text": term
            })

    # MISLEADING CLAIMS
    risky_patterns = [
        "guaranteed",
        "best in the world",
        "number one",
        "#1",
        "risk-free",
        "100% safe",
        "100% effective",
        "100% secure",
        "limited time only",
        "act now"
    ]

    for phrase in risky_patterns:

        if phrase in text:
            add_finding(
                "high",
                "Potentially misleading or high-pressure claim.",
                phrase
            )

    # URL CHECK
    if re.search(r"https?://\S+|www\.\S+", content, re.I):
        add_finding(
            "low",
            "External URL detected. Verify that it is approved."
        )

    # PUNCTUATION CHECK
    if "!!" in content or "??" in content:
        add_finding(
            "low",
            "Excessive punctuation may not match the brand tone."
        )

    # CAPITAL LETTER CHECK
    caps_words = re.findall(
        r"\b[A-Z]{4,}\b",
        content
    )

    if caps_words:
        add_finding(
            "low",
            "Excessive uppercase wording detected.",
            ", ".join(caps_words[:5])
        )

    # BRAND NAME CHECK
    brand_name = guidelines["brand_name"]

    if brand_name and brand_name.lower() not in text:
        add_finding(
            "notice",
            "Brand name was not mentioned in the content.",
            brand_name
        )

    score = max(0, min(100, score))

    return {
        "score": score,
        "status": "compliant" if not findings else "needs_review",
        "findings": findings,
        "analysis_type": "rule-based",
        "message": (
            "Analysis completed. Final approval requires human review."
        )
    }


# =========================================================
# REVIEW SERIALIZATION
# =========================================================

def row_to_review(row):

    return {
        "id": row["id"],
        "content": row["content"],
        "score": row["score"],
        "status": row["status"],
        "findings": json.loads(row["findings"] or "[]"),
        "analysis_type": row["analysis_type"],
        "reviewer": row["reviewer"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


# =========================================================
# HOMEPAGE
# =========================================================

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# =========================================================
# HEALTH API
# =========================================================

@app.route("/api/health", methods=["GET"])
def health():

    try:

        with get_db() as conn:
            conn.execute("SELECT 1")

        return jsonify({
            "status": "ok",
            "application": "Inkloom AI",
            "analysis_engine": "rule-based",
            "database": "connected"
        }), 200

    except Exception:

        app.logger.exception("Health check database error")

        return jsonify({
            "status": "error",
            "application": "Inkloom AI",
            "database": "unavailable"
        }), 500


# =========================================================
# TEMPORARY DEBUG ROUTE
# =========================================================

@app.route("/debug-test", methods=["GET"])
def debug_test():
    return "DEBUG ROUTE WORKING", 200


# =========================================================
# LOGIN API
# =========================================================

@app.route("/api/login", methods=["POST"])
def login():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({
            "error": "Email and password are required."
        }), 400

    with get_db() as conn:

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

    if not user or not check_password_hash(
        user["password"], password
    ):
        return jsonify({
            "error": "Invalid email or password."
        }), 401

    session["user"] = user["email"]
    session["name"] = user["name"]
    session["role"] = user["role"]

    add_audit_log("LOGIN", "User logged in")

    return jsonify({
        "message": "Login successful.",
        "user": {
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        }
    }), 200


# =========================================================
# CURRENT USER API
# =========================================================

@app.route("/api/me", methods=["GET"])
@login_required
def current_user():

    return jsonify({
        "name": session.get("name"),
        "email": session.get("user"),
        "role": session.get("role")
    })


# =========================================================
# LOGOUT API
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({
        "message": "Logged out successfully."
    })


# =========================================================
# GUIDELINES API
# =========================================================

@app.route("/api/guidelines", methods=["GET"])
def guidelines_api():
    return jsonify(get_guidelines())


@app.route("/api/guidelines", methods=["POST"])
@login_required
def update_guidelines():

    data = request.get_json(silent=True) or {}

    current = get_guidelines()

    brand_name = data.get(
        "brand_name",
        current["brand_name"]
    )

    tone = data.get(
        "tone",
        current["tone"]
    )

    approved_terms = normalize_terms(
        data.get("approved_terms", current["approved_terms"])
    )

    forbidden_terms = normalize_terms(
        data.get("forbidden_terms", current["forbidden_terms"])
    )

    required_terms = normalize_terms(
        data.get("required_terms", current["required_terms"])
    )

    with get_db() as conn:

        conn.execute("""
            UPDATE guidelines
            SET brand_name = ?,
                tone = ?,
                approved_terms = ?,
                forbidden_terms = ?,
                required_terms = ?,
                updated_at = ?
            WHERE id = (
                SELECT id FROM guidelines
                ORDER BY id DESC LIMIT 1
            )
        """, (
            brand_name,
            tone,
            json.dumps(approved_terms),
            json.dumps(forbidden_terms),
            json.dumps(required_terms),
            now_iso()
        ))

    add_audit_log(
        "GUIDELINES_UPDATED",
        "Brand guidelines updated"
    )

    return jsonify({
        "message": "Guidelines updated successfully.",
        "guidelines": get_guidelines()
    })


# =========================================================
# CONTENT ANALYSIS API
# =========================================================

@app.route("/api/analyse", methods=["POST"])
def analyse_api():

    data = request.get_json(silent=True) or {}

    content = data.get("content", "").strip()

    if not content:
        return jsonify({
            "error": "Please enter content to analyse."
        }), 400

    if len(content) > MAX_ANALYSIS_LENGTH:
        return jsonify({
            "error": "Content is too long."
        }), 400

    result = analyse_content(content)

    with get_db() as conn:

        cursor = conn.execute("""
            INSERT INTO reviews (
                content,
                score,
                status,
                findings,
                analysis_type,
                reviewer,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            content,
            result["score"],
            "pending",
            json.dumps(result["findings"]),
            result["analysis_type"],
            session.get("user", "guest"),
            now_iso(),
            now_iso()
        ))

        review_id = cursor.lastrowid

    add_audit_log(
        "CONTENT_ANALYSED",
        f"Review ID: {review_id}"
    )

    return jsonify({
        "id": review_id,
        "content": content,
        "score": result["score"],
        "status": "pending",
        "findings": result["findings"],
        "analysis_type": result["analysis_type"],
        "message": result["message"]
    }), 200


# =========================================================
# REVIEW HISTORY API
# =========================================================

@app.route("/api/reviews", methods=["GET"])
def reviews_api():

    with get_db() as conn:

        rows = conn.execute("""
            SELECT * FROM reviews
            ORDER BY id DESC
        """).fetchall()

    reviews = [row_to_review(row) for row in rows]

    return jsonify({
        "reviews": reviews,
        "total": len(reviews)
    })


# =========================================================
# SINGLE REVIEW API
# =========================================================

@app.route("/api/reviews/<int:review_id>", methods=["GET"])
def single_review(review_id):

    with get_db() as conn:

        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?",
            (review_id,)
        ).fetchone()

    if not row:
        return jsonify({
            "error": "Review not found."
        }), 404

    return jsonify(row_to_review(row))


# =========================================================
# REVIEW DECISION API
# =========================================================

@app.route(
    "/api/reviews/<int:review_id>/decision",
    methods=["POST"]
)
def review_decision(review_id):

    data = request.get_json(silent=True) or {}

    decision = data.get("decision", "").strip().lower()

    allowed = ["approved", "rejected", "changes"]

    if decision not in allowed:
        return jsonify({
            "error": "Invalid decision. Use approved, rejected or changes."
        }), 400

    with get_db() as conn:

        review = conn.execute(
            "SELECT * FROM reviews WHERE id = ?",
            (review_id,)
        ).fetchone()

        if not review:
            return jsonify({
                "error": "Review not found."
            }), 404

        conn.execute("""
            UPDATE reviews
            SET status = ?,
                reviewer = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            decision,
            session.get("user", "guest"),
            now_iso(),
            review_id
        ))

    add_audit_log(
        "REVIEW_DECISION",
        f"Review {review_id}: {decision}"
    )

    return jsonify({
        "message": "Review decision saved.",
        "id": review_id,
        "status": decision
    })


# =========================================================
# AUDIT LOG API
# =========================================================

@app.route("/api/audit", methods=["GET"])
def audit_api():

    with get_db() as conn:

        rows = conn.execute("""
            SELECT * FROM audit_logs
            ORDER BY id DESC
            LIMIT 100
        """).fetchall()

    logs = []

    for row in rows:

        logs.append({
            "id": row["id"],
            "action": row["action"],
            "details": row["details"],
            "user_email": row["user_email"],
            "created_at": row["created_at"]
        })

    return jsonify({
        "logs": logs,
        "total": len(logs)
    })


# =========================================================
# ANALYTICS API
# =========================================================

@app.route("/api/analytics", methods=["GET"])
def analytics_api():

    with get_db() as conn:

        total = conn.execute(
            "SELECT COUNT(*) FROM reviews"
        ).fetchone()[0]

        approved = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE status = 'approved'"
        ).fetchone()[0]

        rejected = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE status = 'rejected'"
        ).fetchone()[0]

        pending = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE status = 'pending'"
        ).fetchone()[0]

        average = conn.execute(
            "SELECT AVG(score) FROM reviews"
        ).fetchone()[0]

    return jsonify({
        "total_reviews": total,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "average_score": round(average, 2) if average is not None else 0
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "error": "Request is too large. Maximum size is 2 MB."
    }), 413


@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "error": "Requested page or API endpoint was not found."
    }), 404


@app.errorhandler(Exception)
def handle_exception(error):

    if isinstance(error, HTTPException):
        return jsonify({
            "error": error.description
        }), error.code

    app.logger.error(
        "Unexpected server error:\n%s",
        traceback.format_exc()
    )

    return jsonify({
        "error": "An unexpected server error occurred."
    }), 500


# =========================================================
# APPLICATION STARTUP
# =========================================================

try:
    init_db()
    app.logger.info(
        "Inkloom AI database initialized successfully."
    )

except Exception:
    app.logger.exception(
        "Database initialization failed."
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
