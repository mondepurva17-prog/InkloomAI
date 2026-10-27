from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import HTTPException
import sqlite3
import json
import re
from datetime import datetime, timezone
from pathlib import Path

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inkloom.db"

REVIEW_COLUMNS = {
    "id", "content", "analysis", "compliance_score",
    "decision", "reviewer_note", "created_at", "updated_at"
}
GUIDELINE_COLUMNS = {"id", "data", "updated_at"}


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
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


def ensure_schema(conn):
    # Drop tables created by older versions so they are recreated correctly.
    for table, expected in (
        ("reviews", REVIEW_COLUMNS),
        ("guidelines", GUIDELINE_COLUMNS),
    ):
        cols = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})")
        }
        if cols and not expected.issubset(cols):
            conn.execute(f"DROP TABLE {table}")


def init_db():
    with get_db() as conn:
        ensure_schema(conn)

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

        existing = conn.execute(
            "SELECT id FROM guidelines WHERE id = 1"
        ).fetchone()

        if existing is None:
            conn.execute(
                """INSERT INTO guidelines (id, data, updated_at)
                   VALUES (1, ?, ?)""",
                (json.dumps(default_guidelines()), now_iso())
            )


def get_guidelines():
    with get_db() as conn:
        row = conn.execute(
            "SELECT data FROM guidelines WHERE id = 1"
        ).fetchone()

    defaults = default_guidelines()

    if not row:
        return defaults

    try:
        saved = json.loads(row["data"])
        if isinstance(saved, dict):
            defaults.update(saved)
    except (json.JSONDecodeError, TypeError):
        pass

    return defaults


# ---------------- GUIDELINE HELPERS ----------------

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

    aliases = {
        "brand_name": ("brand_name", "name"),
        "brand_tone": ("brand_tone", "tone"),
        "approved_terms": ("approved_terms", "approved_words"),
        "forbidden_terms": (
            "forbidden_terms",
            "restricted_terms",
            "banned_terms"
        ),
        "required_terms": (
            "required_terms",
            "required_phrases"
        ),
        "brand_facts": ("brand_facts", "facts")
    }

    for target, keys in aliases.items():
        for key in keys:
            if key not in payload:
                continue

            value = payload[key]

            if target in (
                "approved_terms",
                "forbidden_terms",
                "required_terms"
            ):
                result[target] = normalise_terms(value)

            elif target == "brand_facts":
                if isinstance(value, (dict, list)):
                    result[target] = value
                else:
                    result[target] = str(value or "").strip()

            else:
                result[target] = str(value or "").strip()

            break

    return result


# ---------------- CONTENT ANALYSIS ----------------

def analyse_content(content, guidelines):
    """
    Rule-based brand governance analysis.

    The compliance score is a heuristic indicator.
    It is not a trained AI model confidence score.
    """

    findings = []
    lower_content = content.casefold()

    forbidden = normalise_terms(
        guidelines.get("forbidden_terms", [])
    )
    required = normalise_terms(
        guidelines.get("required_terms", [])
    )

    # 1. Detect restricted terms.
    for term in forbidden:
        pattern = re.compile(
            r"(?<!\w)" + re.escape(term) + r"(?!\w)",
            re.IGNORECASE
        )

        if pattern.search(content):
            findings.append({
                "title": "Restricted term detected",
                "category": "Brand guidelines",
                "severity": "high",
                "message": (
                    f'The restricted term "{term}" appears '
                    "in your content."
                ),
                "suggestion": (
                    f'Remove "{term}" or replace it with '
                    "a verified, compliant statement."
                )
            })

    # 2. Check required phrases.
    for phrase in required:
        if phrase.casefold() not in lower_content:
            findings.append({
                "title": "Required phrase missing",
                "category": "Brand guidelines",
                "severity": "medium",
                "message": (
                    f'The required phrase "{phrase}" '
                    "was not found."
                ),
                "suggestion": (
                    f'Include "{phrase}" where it fits naturally.'
                )
            })

    # 3. Detect potentially misleading claims.
    patterns = [
        (
            r"\bguaranteed\b",
            "Absolute claim",
            "high",
            "Avoid guarantees unless approved and substantiated."
        ),
        (
            r"\b(best|number\s*one|#1)\b",
            "Unsubstantiated superiority claim",
            "medium",
            "Provide evidence for comparative claims."
        ),
        (
            r"\b(risk[- ]free|100%\s*(safe|effective|secure))\b",
            "Absolute assurance",
            "high",
            "Avoid absolute assurances unless substantiated."
        ),
        (
            r"\b(act now|limited time only|claim your reward)\b",
            "High-pressure language",
            "medium",
            "Use clear, low-pressure wording."
        )
    ]

    for pattern, title, severity, suggestion in patterns:
        matches = re.findall(
            pattern, content, flags=re.IGNORECASE
        )

        if matches:
            findings.append({
                "title": title,
                "category": "Messaging risk",
                "severity": severity,
                "message": (
                    "Potentially risky marketing wording was detected."
                ),
                "suggestion": suggestion
            })

    # 4. Detect URLs.
    if re.search(
        r"(https?://|www\.|bit\.ly/|tinyurl\.com/)",
        content,
        flags=re.IGNORECASE
    ):
        findings.append({
            "title": "Link detected",
            "category": "Link review",
            "severity": "notice",
            "message": (
                "The content contains a URL or shortened link. "
                "This check does not verify the destination."
            ),
            "suggestion": (
                "Verify that the destination is official and safe."
            )
        })

    # 5. Detect excessive punctuation.
    if re.search(r"!{2,}", content):
        findings.append({
            "title": "Excessive punctuation",
            "category": "Tone",
            "severity": "low",
            "message": (
                "Repeated exclamation marks may make the message "
                "feel overly promotional."
            ),
            "suggestion": (
                "Use standard punctuation for a professional tone."
            )
        })

    # 6. Detect all-caps words.
    if re.search(r"\b[A-Z]{5,}\b", content):
        findings.append({
            "title": "All-caps wording",
            "category": "Tone",
            "severity": "low",
            "message": "A word written in all capitals was detected.",
            "suggestion": (
                "Use sentence case unless the word is an approved acronym."
            )
        })

    # 7. Check configured brand name consistency.
    brand_name = str(
        guidelines.get("brand_name") or ""
    ).strip()

    if brand_name:
        alternatives = ["Inkloom", "Inkloom AI"]

        for alternative in alternatives:
            if (
                alternative.casefold() != brand_name.casefold()
                and alternative.casefold() in lower_content
            ):
                findings.append({
                    "title": "Brand name consistency",
                    "category": "Brand identity",
                    "severity": "low",
                    "message": (
                        f'The name "{alternative}" appears, while '
                        f'the configured brand name is "{brand_name}".'
                    ),
                    "suggestion": (
                        f'Use "{brand_name}" consistently when '
                        "referring to your brand."
                    )
                })
                break

    # 8. Calculate a heuristic compliance score.
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

    if not findings:
        summary = (
            "No issues were detected by the configured rule checks. "
            "A human review is still recommended."
        )
    elif any(
        item["severity"] == "high"
        for item in findings
    ):
        summary = (
            "High-priority wording needs review before this content "
            "is approved."
        )
    else:
        summary = (
            "Some items may need revision to better align with "
            "the brand guidelines."
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
            "This score is calculated from configured rules and "
            "detected patterns. It is not AI model confidence."
        )
    }


# ---------------- REVIEW SERIALISATION ----------------

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


# ---------------- WEBSITE ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------- HEALTH CHECK ----------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "application": "Inkloom AI"
    })


# ---------------- GUIDELINES API ----------------

@app.route("/api/guidelines", methods=["GET", "POST"])
def guidelines_api():
    if request.method == "GET":
        current = get_guidelines()

        return jsonify({
            "guidelines": current,
            **current
        })

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "error": "Request body must be a JSON object."
        }), 400

    updated = normalise_guidelines(payload)

    with get_db() as conn:
        conn.execute(
            """
            UPDATE guidelines
            SET data = ?, updated_at = ?
            WHERE id = 1
            """,
            (
                json.dumps(updated, ensure_ascii=False),
                now_iso()
            )
        )

    return jsonify({
        "success": True,
        "message": "Brand guidelines saved successfully.",
        "guidelines": updated
    })


# ---------------- ANALYSIS API ----------------

@app.route("/api/analyse", methods=["POST"])
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

    if len(content) > 100000:
        return jsonify({
            "error": "Content is too long. Limit is 100,000 characters."
        }), 413

    guidelines = get_guidelines()
    analysis = analyse_content(content, guidelines)
    timestamp = now_iso()

    with get_db() as conn:
        cursor = conn.execute(
            """
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
            """,
            (
                content,
                json.dumps(analysis, ensure_ascii=False),
                analysis["compliance_score"],
                timestamp,
                timestamp
            )
        )

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


# ---------------- REVIEW HISTORY API ----------------

@app.route("/api/reviews", methods=["GET"])
def reviews_api():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM reviews
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()

    reviews = [row_to_review(row) for row in rows]

    return jsonify({
        "reviews": reviews,
        "count": len(reviews)
    })


# ---------------- HUMAN REVIEW DECISION API ----------------

@app.route(
    "/api/reviews/<int:review_id>/decision",
    methods=["POST"]
)
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
        "rejected": "Rejected",
        "changes": "Changes Requested",
        "changes requested": "Changes Requested"
    }

    if decision not in allowed:
        return jsonify({
            "error": (
                "Decision must be approved, rejected, or changes."
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

    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM reviews WHERE id = ?",
            (review_id,)
        ).fetchone()

        if row is None:
            return jsonify({
                "error": "Review not found."
            }), 404

        conn.execute(
            """
            UPDATE reviews
            SET decision = ?,
                reviewer_note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                allowed[decision],
                note,
                now_iso(),
                review_id
            )
        )

    return jsonify({
        "success": True,
        "message": f"Decision saved: {allowed[decision]}.",
        "review_id": review_id,
        "decision": allowed[decision],
        "reviewer_note": note
    })


# ---------------- ERROR HANDLERS ----------------

@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({
        "error": "Request too large. Maximum size is 2 MB."
    }), 413


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "API endpoint not found."
        }), 404

    return "Page not found.", 404


@app.errorhandler(Exception)
def internal_error(error):
    # Normal HTTP errors (405, 400, ...) keep their own status code.
    if isinstance(error, HTTPException):
        return jsonify({
            "error": error.description
        }), error.code

    app.logger.exception("Unexpected server error")

    return jsonify({
        "error": f"{type(error).__name__}: {error}"
    }), 500


# Initialise the database when the application starts.
init_db()


if __name__ == "__main__":
    import os
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT",5000)),
        debug=False
    )