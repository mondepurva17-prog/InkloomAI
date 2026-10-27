"use strict";

/* ==========================================
   INKLOOM AI — Frontend Application
   Connects to the existing Flask API
========================================== */

const API = {
    guidelines: "/api/guidelines",
    analyse: "/api/analyse",
    reviews: "/api/reviews",
    upload: "/api/upload"
};

const $ = (id) => document.getElementById(id);

let latestAnalysis = null;
let latestContent = "";
let currentReviewId = null;
let guidelinesData = {};

// ---------- Helpers ----------

async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            ...(options.body instanceof FormData
                ? {}
                : { "Content-Type": "application/json" }),
            ...(options.headers || {})
        }
    });

    const text = await response.text();
    let data = {};

    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        throw new Error(
            `The server returned an invalid response. HTTP ${response.status}.`
        );
    }

    if (!response.ok) {
        throw new Error(
            data.error || data.message ||
            `Request failed with HTTP ${response.status}.`
        );
    }

    return data;
}

function showMessage(id, message, type = "info") {
    const element = $(id);
    if (!element) return;

    element.textContent = message;
    element.dataset.type = type;
    element.style.display = "block";
}

function hideMessage(id) {
    const element = $(id);
    if (element) element.textContent = "";
}

function setButtonLoading(button, loading, loadingText = "Analyzing...") {
    if (!button) return;

    if (loading) {
        button.dataset.originalText = button.textContent;
        button.disabled = true;
        button.textContent = loadingText;
    } else {
        button.disabled = false;
        button.textContent =
            button.dataset.originalText || "Analyze Content";
        delete button.dataset.originalText;
    }
}

function splitLines(value) {
    return String(value || "")
        .split(/\r?\n|,/)
        .map(item => item.trim())
        .filter(Boolean);
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

function firstValue(object, keys, fallback = "") {
    for (const key of keys) {
        if (object && object[key] !== undefined && object[key] !== null) {
            return object[key];
        }
    }
    return fallback;
}

// ---------- Navigation ----------

function initNavigation() {
    document.querySelectorAll("[data-view]").forEach(button => {
        button.addEventListener("click", () => {
            const target = button.dataset.view;

            document.querySelectorAll("[data-view]").forEach(item => {
                item.classList.toggle("active", item === button);
                item.setAttribute(
                    "aria-current",
                    item === button ? "page" : "false"
                );
            });

            document.querySelectorAll(
                "#review-view, #guidelines-view, #history-view"
            ).forEach(view => {
                view.hidden = view.id !== `${target}-view`;
                view.classList.toggle("active", view.id === `${target}-view`);
            });

            if (target === "history") loadHistory();
            if (target === "guidelines") loadGuidelines();
        });
    });
}

// ---------- Content input ----------

function initContentInput() {
    const input = $("content-input");
    const counter = $("character-count");

    if (input && counter) {
        const updateCount = () => {
            counter.textContent = input.value.length.toLocaleString();
        };

        input.addEventListener("input", updateCount);
        updateCount();
    }

    $("load-sample")?.addEventListener("click", () => {
        if (!input) return;

        input.value =
            "Congratulations! You are guaranteed to win ₹50,000. " +
            "This is the best product ever!!! Click this link now " +
            "to claim your reward.";

        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
    });

    $("file-input")?.addEventListener("change", handleFileUpload);
}

// ---------- Brand guidelines ----------

async function loadGuidelines() {
    try {
        const data = await apiRequest(API.guidelines);
        guidelinesData = data.guidelines || data.data || data;

        const g = guidelinesData;

        if ($("brand-name")) {
            $("brand-name").value =
                firstValue(g, ["brand_name", "name"], "");
        }

        if ($("brand-tone")) {
            $("brand-tone").value =
                firstValue(g, ["brand_tone", "tone"], "");
        }

        if ($("approved-terms")) {
            $("approved-terms").value =
                formatList(firstValue(g, [
                    "approved_terms", "approved_words"
                ], []));
        }

        if ($("forbidden-terms")) {
            $("forbidden-terms").value =
                formatList(firstValue(g, [
                    "forbidden_terms", "restricted_terms",
                    "banned_terms"
                ], []));
        }

        if ($("required-terms")) {
            $("required-terms").value =
                formatList(firstValue(g, [
                    "required_terms", "required_phrases"
                ], []));
        }

        if ($("brand-facts")) {
            $("brand-facts").value =
                formatFacts(firstValue(g, [
                    "brand_facts", "facts"
                ], ""));
        }

        renderActiveRules();
    } catch (error) {
        console.error("Guidelines loading error:", error);
        showMessage(
            "guidelines-message",
            `Could not load guidelines: ${error.message}`,
            "error"
        );
    }
}

function formatList(value) {
    if (Array.isArray(value)) return value.join("\n");
    return String(value || "");
}

function formatFacts(value) {
    if (Array.isArray(value)) return value.join("\n");
    if (typeof value === "object" && value !== null) {
        return Object.entries(value)
            .map(([key, val]) => `${key}: ${val}`)
            .join("\n");
    }
    return String(value || "");
}

function renderActiveRules() {
    const container = $("active-rules");
    if (!container) return;

    const approved = splitLines($("approved-terms")?.value || "");
    const forbidden = splitLines($("forbidden-terms")?.value || "");
    const required = splitLines($("required-terms")?.value || "");

    container.innerHTML = `
        <div class="rule-summary">
            <span class="rule-dot"></span>
            <span>Approved terms</span>
            <strong>${approved.length}</strong>
        </div>
        <div class="rule-summary">
            <span class="rule-dot forbidden"></span>
            <span>Restricted terms</span>
            <strong>${forbidden.length}</strong>
        </div>
        <div class="rule-summary">
            <span class="rule-dot required"></span>
            <span>Required phrases</span>
            <strong>${required.length}</strong>
        </div>
    `;
}

async function saveGuidelines(event) {
    event.preventDefault();

    const payload = {
        brand_name: $("brand-name")?.value.trim() || "",
        brand_tone: $("brand-tone")?.value.trim() || "",
        approved_terms: splitLines($("approved-terms")?.value),
        forbidden_terms: splitLines($("forbidden-terms")?.value),
        required_terms: splitLines($("required-terms")?.value),
        brand_facts: $("brand-facts")?.value.trim() || ""
    };

    try {
        const result = await apiRequest(API.guidelines, {
            method: "POST",
            body: JSON.stringify(payload)
        });

        guidelinesData = result.guidelines || payload;

        showMessage(
            "guidelines-message",
            result.message || "Brand guidelines saved successfully.",
            "success"
        );

        renderActiveRules();
    } catch (error) {
        console.error("Saving guidelines error:", error);
        showMessage(
            "guidelines-message",
            `Could not save guidelines: ${error.message}`,
            "error"
        );
    }
}

// ---------- Analysis ----------

async function analyseContent() {
  const contentInput = $("content-input");
const content = contentInput.value.trim();

if (!content) {
    const status = $("analysis-status");
    status.textContent = "Please enter content to analyze.";
    status.style.color = "#ff6b6b";
    contentInput.focus();
    return;
}
    const input = $("content-input");
    const button = $("analyze-button");
    const content = input?.value.trim() || "";

    hideMessage("decision-message");

    if (!content) {
        showMessage(
            "analysis-status",
            "Please paste some content before starting the analysis.",
            "error"
        );
        input?.focus();
        return;
    }

    latestContent = content;
    latestAnalysis = null;
    currentReviewId = null;

    setButtonLoading(button, true, "Analyzing content...");

    showMessage(
        "analysis-status",
        "Checking your content against the brand guidelines...",
        "info"
    );

    if ($("findings-list")) {
        $("findings-list").innerHTML =
            `<p class="empty-state">Analysis in progress...</p>`;
    }

    try {
        const result = await apiRequest(API.analyse, {
            method: "POST",
            body: JSON.stringify({
                content: content,
                text: content,
                message: content
            })
        });

        latestAnalysis = result;

        const analysis = result.analysis || result.result || result;
        currentReviewId = firstValue(result, [
            "review_id", "id"
        ], firstValue(analysis, ["review_id", "id"], null));

        const score = Number(firstValue(analysis, [
            "compliance_score", "score", "risk_score"
        ], firstValue(result, [
            "compliance_score", "score", "risk_score"
        ], 0)));

        renderScore(score, analysis);
        renderFindings(analysis, result);

        const findingItems = getFindings(analysis, result);
        const status = findingItems.length
            ? `Analysis complete — ${findingItems.length} finding(s) detected.`
            : "Analysis complete. No findings were returned by the backend.";

        showMessage("analysis-status", status, "success");

        if (!findingItems.length && !hasKnownResult(analysis, result)) {
            $("findings-list").innerHTML = `
                <div class="finding-card">
                    <h4>Analysis response received</h4>
                    <p>The backend responded, but its result format was not recognised.</p>
                    <pre class="api-debug">${escapeHTML(
                        JSON.stringify(result, null, 2)
                    )}</pre>
                </div>`;
        }

        console.log("Inkloom AI analysis response:", result);
    } catch (error) {
        console.error("Analysis failed:", error);

        showMessage(
            "analysis-status",
            `Analysis failed: ${error.message}. Check the VS Code terminal for the Flask error.`,
            "error"
        );

        if ($("findings-list")) {
            $("findings-list").innerHTML = `
                <div class="finding-card">
                    <h4>Could not complete analysis</h4>
                    <p>${escapeHTML(error.message)}</p>
                    <p>Check that Flask is running and that the API route is available.</p>
                </div>`;
        }
    } finally {
        setButtonLoading(button, false);
    }
}

function getFindings(analysis, result) {
    const findings = firstValue(analysis, [
        "findings", "issues", "violations", "checks", "results"
    ], firstValue(result, [
        "findings", "issues", "violations", "checks", "results"
    ], []));

    if (typeof findings === "string") {
        return findings ? [{ message: findings }] : [];
    }

    if (!Array.isArray(findings)) return [];
    return findings;
}

function hasKnownResult(analysis, result) {
    return [
        "compliance_score", "score", "risk_score",
        "findings", "issues", "violations", "checks", "results",
        "summary", "message", "recommendations", "suggestions"
    ].some(key =>
        analysis?.[key] !== undefined || result?.[key] !== undefined
    );
}

function renderScore(score, analysis) {
    const ring = $("score-ring");
    const scoreValue = $("score-value");
    const caption = $("score-caption");
    const count = $("finding-count");

    const safeScore = Math.max(0, Math.min(100, Math.round(score || 0)));

    if (scoreValue) scoreValue.textContent = `${safeScore}%`;

    if (ring) {
        ring.style.setProperty("--score", safeScore);
        ring.setAttribute("aria-label", `Compliance score ${safeScore}%`);
    }

    if (caption) {
        caption.textContent =
            safeScore >= 85 ? "Strong brand alignment" :
            safeScore >= 60 ? "Some improvements needed" :
            "Review recommended";
    }

    if (count) {
        count.textContent = getFindings(analysis, latestAnalysis).length;
    }
}

function renderFindings(analysis, result) {
    const container = $("findings-list");
    if (!container) return;

    const findings = getFindings(analysis, result);
    const summary = firstValue(analysis, [
        "summary", "message", "overall_feedback"
    ], firstValue(result, [
        "summary", "message", "overall_feedback"
    ], ""));

    const suggestions = firstValue(analysis, [
        "suggestions", "recommendations", "improvements"
    ], firstValue(result, [
        "suggestions", "recommendations", "improvements"
    ], []));

    let html = "";

    if (summary) {
        html += `
            <div class="finding-card">
                <h4>Analysis summary</h4>
                <p>${escapeHTML(summary)}</p>
            </div>`;
    }

    if (!findings.length && !summary) {
        html += `
            <div class="finding-card">
                <h4>No findings listed</h4>
                <p>The server returned no issues. Review the score and response below.</p>
            </div>`;
    }

    html += findings.map((finding, index) => {
        const item = typeof finding === "string"
            ? { message: finding }
            : finding || {};

        const title = firstValue(item, [
            "title", "rule", "category", "type", "name"
        ], `Finding ${index + 1}`);

        const message = firstValue(item, [
            "message", "description", "detail", "issue", "reason", "text"
        ], typeof finding === "string" ? finding : "Review this item.");

        const severity = String(firstValue(item, [
            "severity", "level", "priority"
        ], "notice")).toLowerCase();

        const suggestion = firstValue(item, [
            "suggestion", "recommendation", "fix", "action"
        ], "");

        return `
            <article class="finding-card">
                <div class="finding-heading">
                    <h4>${escapeHTML(title)}</h4>
                    <span class="finding-severity">${escapeHTML(severity)}</span>
                </div>
                <p>${escapeHTML(message)}</p>
                ${suggestion
                    ? `<p class="finding-suggestion"><strong>Suggested fix:</strong> ${escapeHTML(suggestion)}</p>`
                    : ""}
            </article>`;
    }).join("");

    if (Array.isArray(suggestions) && suggestions.length) {
        html += `
            <div class="finding-card">
                <h4>Suggested improvements</h4>
                <ul>
                    ${suggestions.map(item => {
                        const value = typeof item === "string"
                            ? item
                            : firstValue(item, ["message", "text", "suggestion"], JSON.stringify(item));
                        return `<li>${escapeHTML(value)}</li>`;
                    }).join("")}
                </ul>
            </div>`;
    }

    container.innerHTML = html;
}

// ---------- File upload ----------

async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const input = $("content-input");
    const extension = file.name.split(".").pop().toLowerCase();

    if (["txt", "md", "csv"].includes(extension)) {
        try {
            const text = await file.text();
            if (input) {
                input.value = text;
                input.dispatchEvent(new Event("input", { bubbles: true }));
            }

            showMessage(
                "analysis-status",
                `${file.name} loaded. Click Analyze to review it.`,
                "success"
            );
        } catch (error) {
            showMessage(
                "analysis-status",
                `Could not read file: ${error.message}`,
                "error"
            );
        }
    } else {
        showMessage(
            "analysis-status",
            "This version supports TXT, MD and CSV files. PDF/image text extraction is not configured.",
            "error"
        );
    }

    event.target.value = "";
}

// ---------- Human review decisions ----------

async function saveDecision(decision) {
    if (!latestAnalysis) {
        showMessage(
            "decision-message",
            "Please analyse the content before recording a decision.",
            "error"
        );
        return;
    }

    const note = $("reviewer-note")?.value.trim() || "";

    if (currentReviewId === null || currentReviewId === undefined) {
        showMessage(
            "decision-message",
            "Analysis completed, but the response did not provide a saved review ID. Check that /api/analyse saves and returns the review ID.",
            "error"
        );
        return;
    }

    try {
        const result = await apiRequest(
            `${API.reviews}/${encodeURIComponent(currentReviewId)}/decision`,
            {
                method: "POST",
                body: JSON.stringify({
                    decision: decision,
                    reviewer_note: note,
                    note: note
                })
            }
        );

        showMessage(
            "decision-message",
            result.message || `Decision recorded: ${decision}.`,
            "success"
        );

        loadHistory();
    } catch (error) {
        console.error("Decision save failed:", error);
        showMessage(
            "decision-message",
            `Could not save decision: ${error.message}`,
            "error"
        );
    }
}

// ---------- Review history ----------

async function loadHistory() {
    const container = $("history-list");
    if (!container) return;

    container.innerHTML = `<p class="empty-state">Loading review history...</p>`;

    try {
        const data = await apiRequest(API.reviews);
        const reviews = Array.isArray(data)
            ? data
            : firstValue(data, ["reviews", "history", "data"], []);

        if (!Array.isArray(reviews) || !reviews.length) {
            container.innerHTML =
                `<p class="empty-state">No saved reviews yet. Analyse some content first.</p>`;
            return;
        }

        container.innerHTML = reviews.map(review => {
            const id = firstValue(review, ["id", "review_id"], "—");
            const content = String(firstValue(review, [
                "content", "text", "message"
            ], "Content unavailable"));
            const score = firstValue(review, [
                "compliance_score", "score", "risk_score"
            ], "—");
            const decision = firstValue(review, [
                "decision", "status"
            ], "pending");
            const created = firstValue(review, [
                "created_at", "timestamp", "date"
            ], "");

            return `
                <article class="finding-card">
                    <div class="finding-heading">
                        <h4>Review #${escapeHTML(id)}</h4>
                        <span class="finding-severity">${escapeHTML(decision)}</span>
                    </div>
                    <p>${escapeHTML(content.slice(0, 200))}${content.length > 200 ? "…" : ""}</p>
                    <p class="finding-suggestion">Score: ${escapeHTML(score)}${created ? " · " + escapeHTML(created) : ""}</p>
                </article>`;
        }).join("");
    } catch (error) {
        console.error("History loading error:", error);
        container.innerHTML =
            `<p class="empty-state">Could not load history: ${escapeHTML(error.message)}</p>`;
    }
}

// ---------- App start ----------

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initContentInput();

    $("analyze-button")?.addEventListener("click", analyseContent);
    $("guidelines-form")?.addEventListener("submit", saveGuidelines);
    $("upload-button")?.addEventListener("click", () => $("file-input")?.click());

    $("approve-button")?.addEventListener("click", () => saveDecision("approved"));
    $("reject-button")?.addEventListener("click", () => saveDecision("rejected"));
    $("request-changes-button")?.addEventListener("click", () => saveDecision("changes"));

    loadGuidelines();
});
