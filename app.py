
from flask import Flask, render_template, request, jsonify, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import json
import re
import os
import logging
import traceback

# =========================================================
# INKLOOM AI - BRAND GOVERNANCE PLATFORM
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "inkloom-ai-development-secret-change-before-deployment"
)

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BASE_DIR = Path(__file__).resolve().parent

# Render writable database directory
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "inkloom.db"

MAX_ANALYSIS_LENGTH = 20000

# Logging configuration
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_guidelines():
    return {
        "brand_name": "Inkloom AI",
        "brand_tone": "Clear, helpful, confident, trustworthy",
        "approved_terms": ["simple", "reliable", "thoughtful"],
        "forbidden_terms": ["guaranteed", "risk-free", "100% cure"],
        "required_terms": [],
        "brand_facts": ""
    }


def init_db():

    with get_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS guidelines (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                analysis TEXT NOT NULL,
                compliance_score INTEGER NOT NULL,
                decision TEXT NOT NULL DEFAULT 'Pending',
                reviewer_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                user_id INTEGER,
                user_name TEXT NOT NULL,
                action TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        existing = conn.execute(
            "SELECT id FROM guidelines WHERE id = 1"
        ).fetchone()

        if existing is None:

            conn.execute("""
                INSERT INTO guidelines (id, data, updated_at)
                VALUES (1, ?, ?)
            """, (json.dumps(default_guidelines()), now_iso()))

        demo_users = [
            ("Admin Demo", "admin@inkloom.demo", "Admin@123", "admin"),
            ("Reviewer Demo", "reviewer@inkloom.demo", "Review@123", "reviewer"),
            ("Creator Demo", "creator@inkloom.demo", "Create@123", "creator")
        ]

        for name, email, password, role in demo_users:

            user = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            ).fetchone()

            if user is None:

                conn.execute("""
                    INSERT INTO users (name, email, password, role)
                    VALUES (?, ?, ?, ?)
                """, (
                    name,
                    email,
                    generate_password_hash(password),
                    role
                ))


def get_guidelines():

    defaults = default_guidelines()

    with get_db() as conn:

        row = conn.execute(
            "SELECT data FROM guidelines WHERE id = 1"
        ).fetchone()

    if row:

        try:
            saved = json.loads(row["data"])

            if isinstance(saved, dict):
                defaults.update(saved)

        except (json.JSONDecodeError, TypeError):
            app.logger.exception("Unable to read saved guidelines")

    return defaults


# =========================================================
# LOGIN AND ROLE HELPERS
# =========================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            return jsonify({
                "success": False,
                "error": "Please sign in to continue."
            }), 401

        return function(*args, **kwargs)

    return wrapper


def reviewer_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            return jsonify({
                "success": False,
                "error": "Please sign in to continue."
            }), 401

        if session.get("user_role") not in ["admin", "reviewer"]:

            return jsonify({
                "success": False,
                "error": "Only admins and reviewers can access this."
            }), 403

        return function(*args, **kwargs)

    return wrapper


# =========================================================
# GUIDELINE HELPERS
# =========================================================

def normalise_terms(value):

    if isinstance(value, list):

        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, str):

        return [
            item.strip()
            for item in re.split(r"[\n,]+", value)
            if item.strip()
        ]

    return []


def normalise_guidelines(payload):

    result = get_guidelines()

    for key in ["brand_name", "brand_tone", "brand_facts"]:

        if key in payload:
            result[key] = str(payload[key] or "").strip()

    for key in [
        "approved_terms",
        "forbidden_terms",
        "required_terms"
    ]:

        if key in payload:
            result[key] = normalise_terms(payload[key])

    return result


# =========================================================
# CONTENT ANALYSIS ENGINE
# =========================================================

def add_finding(findings, title, category, severity, message, suggestion):

    findings.append({
        "title": title,
        "category": category,
        "severity": severity,
        "message": message,
        "suggestion": suggestion
    })


def analyse_content(content, guidelines):

    findings = []
    lower_content = content.casefold()

    forbidden = normalise_terms(
        guidelines.get("forbidden_terms", [])
    )

    required = normalise_terms(
        guidelines.get("required_terms", [])
    )

    approved = normalise_terms(
        guidelines.get("approved_terms", [])
    )

    # Restricted terms
    for term in forbidden:

        pattern = re.compile(
            r"(?<!\w)" + re.escape(term) + r"(?!\w)",
            re.IGNORECASE
        )

        if pattern.search(content):

            add_finding(
                findings,
                "Restricted term detected",
                "Brand guidelines",
                "high",
                f'The restricted term "{term}" appears in your content.',
                f'Remove "{term}" or replace it with a compliant statement.'
            )

    # Required phrases
    for phrase in required:

        if phrase.casefold() not in lower_content:

            add_finding(
                findings,
                "Required phrase missing",
                "Brand guidelines",
                "medium",
                f'The required phrase "{phrase}" was not found.',
                f'Include "{phrase}" where it fits naturally.'
            )

    # Approved terminology
    if approved:

        found = [
            term for term in approved
            if term.casefold() in lower_content
        ]

        if not found:

            add_finding(
                findings,
                "Approved terminology not used",
                "Brand voice",
                "low",
                "None of the configured approved terms were found.",
                "Consider using approved brand terminology."
            )

    # Marketing language checks
    patterns = [
        (
            r"\bguaranteed\b",
            "Absolute claim",
            "high",
            "Potentially absolute wording was detected.",
            "Avoid guarantees unless the claim is approved and supported."
        ),
        (
            r"\b(best|number\s+one|#1)\b",
            "Unsubstantiated superiority claim",
            "medium",
            "A comparative or superiority claim was detected.",
            "Provide evidence or use more balanced wording."
        ),
        (
            r"\b(risk[- ]free|100%\s+(safe|effective|secure))\b",
            "Absolute assurance",
            "high",
            "An absolute assurance was detected.",
            "Avoid absolute assurances unless substantiated."
        ),
        (
            r"\b(act now|limited time only|claim your reward)\b",
            "High-pressure language",
            "medium",
            "Potentially high-pressure language was detected.",
            "Use clear and low-pressure wording."
        )
    ]

    for pattern, title, severity, message, suggestion in patterns:

        if re.search(pattern, content, re.IGNORECASE):

            add_finding(
                findings,
                title,
                "Messaging risk",
                severity,
                message,
                suggestion
            )

    # Links
    if re.search(
        r"(https?://|www\.|bit\.ly/|tinyurl\.com/)",
        content,
        re.IGNORECASE
    ):

        add_finding(
            findings,
            "Link detected",
            "Link review",
            "notice",
            "The content contains a URL or shortened link.",
            "Verify that the destination is official and safe."
        )

    # Excessive punctuation
    if re.search(r"!{2,}", content):

        add_finding(
            findings,
            "Excessive punctuation",
            "Tone",
            "low",
            "Repeated exclamation marks may feel overly promotional.",
            "Use standard punctuation."
        )

    # All caps
    capital_words = re.findall(r"\b[A-Z]{5,}\b", content)

    if capital_words:

        add_finding(
            findings,
            "All-caps wording",
            "Tone",
            "low",
            f'All-caps wording was detected: "{capital_words[0]}".',
            "Use sentence case unless it is an approved acronym."
        )

    weights = {
        "high": 25,
        "medium": 15,
        "low": 7,
        "notice": 3
    }

    deductions = sum(
        weights.get(item["severity"], 3)
        for item in findings
    )

    score = max(0, min(100, 100 - deductions))

    high_count = sum(
        item["severity"] == "high"
        for item in findings
    )

    if not findings:

        summary = (
            "No issues were detected by the configured rule checks. "
            "Human review is still recommended."
        )

    elif high_count:

        summary = (
            f"{high_count} high-priority issue(s) detected. "
            "Review the content before approval."
        )

    else:

        summary = (
            "Some improvements may be needed to better align "
            "with the brand guidelines."
        )

    suggestions = list(dict.fromkeys(
        item["suggestion"]
        for item in findings
        if item.get("suggestion")
    ))

    return {
        "compliance_score": score,
        "score": score,
        "summary": summary,
        "findings": findings,
        "suggestions": suggestions,
        "finding_count": len(findings),
        "analysis_type": "rule-based",
        "score_explanation": (
            "This score is calculated using configured rules and "
            "detected patterns. It is not AI model confidence."
        )
    }


# =========================================================
# REVIEW SERIALISATION
# =========================================================

def row_to_review(row):

    try:
        analysis = json.loads(row["analysis"])
    except (json.JSONDecodeError, TypeError):
        analysis = {}

    return {
        "id": row["id"],
        "review_id": row["id"],
        "content": row["content"],
        "analysis": analysis,
        "compliance_score": row["compliance_score"],
        "score": row["compliance_score"],
        "findings": analysis.get("findings", []),
        "suggestions": analysis.get("suggestions", []),
        "summary": analysis.get("summary", ""),
        "decision": row["decision"],
        "reviewer_note": row["reviewer_note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


# =========================================================
# WEBSITE
# =========================================================
@app.route("/")
def index():
    return "Inkloom AI server is working!"


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
        })

    except Exception:

        app.logger.exception("Health check database error")

        return jsonify({
            "status": "error",
            "application": "Inkloom AI",
            "database": "unavailable"
        }), 500


# =========================================================
# LOGIN API
# =========================================================

@app.route("/api/login", methods=["POST"])
def login_api():

    payload = request.get_json(silent=True) or {}

    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or not password:

        return jsonify({
            "success": False,
            "error": "Please enter email and password."
        }), 400

    with get_db() as conn:

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

    if user is None or not check_password_hash(
        user["password"], password
    ):

        return jsonify({
            "success": False,
            "error": "Invalid email or password."
        }), 401

    session.clear()

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        }
    })


# =========================================================
# CURRENT USER API
# =========================================================

@app.route("/api/me", methods=["GET"])
def current_user_api():

    if "user_id" not in session:

        return jsonify({
            "success": True,
            "authenticated": False,
            "user": None
        })

    return jsonify({
        "success": True,
        "authenticated": True,
        "user": {
            "id": session["user_id"],
            "name": session["user_name"],
            "email": session["user_email"],
            "role": session["user_role"]
        }
    })


# =========================================================
# LOGOUT API
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout_api():

    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    })


# =========================================================
# GUIDELINES API
# =========================================================

@app.route("/api/guidelines", methods=["GET", "POST"])
@login_required
def guidelines_api():

    if request.method == "GET":

        current = get_guidelines()

        return jsonify({
            "success": True,
            "guidelines": current,
            **current
        })

    if session.get("user_role") != "admin":

        return jsonify({
            "success": False,
            "error": "Only an admin can update brand guidelines."
        }), 403

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):

        return jsonify({
            "error": "Request body must be a JSON object."
        }), 400

    updated = normalise_guidelines(payload)

    with get_db() as conn:

        conn.execute("""
            UPDATE guidelines
            SET data = ?, updated_at = ?
            WHERE id = 1
        """, (
            json.dumps(updated, ensure_ascii=False),
            now_iso()
        ))

    return jsonify({
        "success": True,
        "message": "Brand guidelines saved successfully.",
        "guidelines": updated
    })


# =========================================================
# ANALYSIS API
# =========================================================

@app.route("/api/analyse", methods=["POST"])
@login_required
def analyse_api():

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):

        return jsonify({
            "error": "Send a JSON object containing content."
        }), 400

    content = (
        payload.get("content")
        or payload.get("text")
        or payload.get("message")
        or ""
    )

    if not isinstance(content, str):

        return jsonify({
            "error": "Content must be text."
        }), 400

    content = content.strip()

    if not content:

        return jsonify({
            "error": "Please provide content to analyse."
        }), 400

    if len(content) > MAX_ANALYSIS_LENGTH:

        return jsonify({
            "error": (
                f"Content is too long. Limit is "
                f"{MAX_ANALYSIS_LENGTH:,} characters."
            )
        }), 413

    guidelines = get_guidelines()
    analysis = analyse_content(content, guidelines)
    timestamp = now_iso()

    with get_db() as conn:

        cursor = conn.execute("""
            INSERT INTO reviews
            (
                content,
                analysis,
                compliance_score,
                decision,
                reviewer_note,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'Pending', '', ?, ?)
        """, (
            content,
            json.dumps(analysis, ensure_ascii=False),
            analysis["compliance_score"],
            timestamp,
            timestamp
        ))

        review_id = cursor.lastrowid

    return jsonify({
        "success": True,
        "id": review_id,
        "review_id": review_id,
        "content": content,
        "analysis": analysis,
        "result": analysis,
        "compliance_score": analysis["compliance_score"],
        "score": analysis["compliance_score"],
        "findings": analysis["findings"],
        "suggestions": analysis["suggestions"],
        "summary": analysis["summary"],
        "finding_count": analysis["finding_count"],
        "decision": "Pending",
        "created_at": timestamp
    })


# =========================================================
# REVIEW HISTORY API
# =========================================================

@app.route("/api/reviews", methods=["GET"])
@login_required
def reviews_api():

    with get_db() as conn:

        rows = conn.execute("""
            SELECT *
            FROM reviews
            ORDER BY id DESC
            LIMIT 50
        """).fetchall()

    reviews = [row_to_review(row) for row in rows]

    return jsonify({
        "success": True,
        "reviews": reviews,
        "count": len(reviews)
    })


# =========================================================
# HUMAN REVIEW DECISION API
# =========================================================

@app.route(
    "/api/reviews/<int:review_id>/decision",
    methods=["POST"]
)
@reviewer_required
def review_decision_api(review_id):

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):

        return jsonify({
            "error": "Request body must be a JSON object."
        }), 400

    decision = str(
        payload.get("decision", "")
    ).strip().lower().replace("_", " ")

    allowed = {
        "approved": "Approved",
        "approve": "Approved",
        "rejected": "Rejected",
        "reject": "Rejected",
        "changes": "Changes Requested",
        "changes requested": "Changes Requested",
        "request changes": "Changes Requested"
    }

    if decision not in allowed:

        return jsonify({
            "error": (
                "Decision must be approved, rejected, "
                "or changes requested."
            )
        }), 400

    note = str(
        payload.get(
            "reviewer_note",
            payload.get("note", "")
        ) or ""
    ).strip()

    if len(note) > 5000:

        return jsonify({
            "error": "Reviewer note is too long."
        }), 400

    timestamp = now_iso()
    final_decision = allowed[decision]

    with get_db() as conn:

        row = conn.execute(
            "SELECT id FROM reviews WHERE id = ?",
            (review_id,)
        ).fetchone()

        if row is None:

            return jsonify({
                "error": "Review not found."
            }), 404

        conn.execute("""
            UPDATE reviews
            SET decision = ?,
                reviewer_note = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            final_decision,
            note,
            timestamp,
            review_id
        ))

        conn.execute("""
            INSERT INTO audit_logs
            (review_id, user_id, user_name, action, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            review_id,
            session.get("user_id"),
            session.get("user_name", "Unknown"),
            final_decision,
            note,
            timestamp
        ))

    return jsonify({
        "success": True,
        "message": f"Decision saved: {final_decision}.",
        "review_id": review_id,
        "decision": final_decision,
        "reviewer_note": note
    })


# =========================================================
# AUDIT LOG API
# =========================================================

@app.route("/api/audit", methods=["GET"])
@reviewer_required
def audit_api():

    with get_db() as conn:

        rows = conn.execute("""
            SELECT *
            FROM audit_logs
            ORDER BY id DESC
            LIMIT 100
        """).fetchall()

    logs = [dict(row) for row in rows]

    return jsonify({
        "success": True,
        "logs": logs,
        "audit_logs": logs
    })


# =========================================================
# ANALYTICS API
# =========================================================

@app.route("/api/analytics", methods=["GET"])
@reviewer_required
def analytics_api():

    with get_db() as conn:

        rows = conn.execute("""
            SELECT id, compliance_score, decision,
                   analysis, created_at
            FROM reviews
            ORDER BY id ASC
        """).fetchall()

    total = len(rows)

    approved = sum(
        row["decision"] == "Approved"
        for row in rows
    )

    pending = sum(
        row["decision"] == "Pending"
        for row in rows
    )

    average_score = round(
        sum(row["compliance_score"] for row in rows) / total,
        1
    ) if total else 0

    violation_counts = {}
    trend = []

    for row in rows:

        try:
            analysis = json.loads(row["analysis"])
        except (json.JSONDecodeError, TypeError):
            analysis = {}

        for finding in analysis.get("findings", []):

            title = finding.get("title", "Other")

            violation_counts[title] = (
                violation_counts.get(title, 0) + 1
            )

        trend.append({
            "id": row["id"],
            "score": row["compliance_score"],
            "created_at": row["created_at"]
        })

    return jsonify({
        "success": True,
        "total_reviews": total,
        "total": total,
        "approved": approved,
        "pending": pending,
        "average_score": average_score,
        "violation_counts": violation_counts,
        "score_trend": trend,
        "trend": trend
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def request_too_large(error):

    return jsonify({
        "error": "Request too large. Please reduce the content size."
    }), 413


@app.errorhandler(404)
def not_found(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "error": "API endpoint not found."
        }), 404

    return "Page not found.", 404


@app.errorhandler(Exception)
def internal_error(error):

    if isinstance(error, HTTPException):
        return error

    # Print complete traceback in Render Runtime Logs
    app.logger.exception("Unexpected server error")

    return jsonify({
        "error": "An unexpected server error occurred."
    }), 500


# =========================================================
# START APPLICATION
# =========================================================

try:

    init_db()
    app.logger.info("Inkloom AI database initialized successfully.")
    app.logger.info("Database path: %s", DB_PATH)

except Exception:

    app.logger.exception("Database initialization failed")
    raise


app.logger.info("Registered application routes:")

for route in app.url_map.iter_rules():
    app.logger.info("%s", route)


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
