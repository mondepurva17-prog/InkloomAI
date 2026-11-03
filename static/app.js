"use strict";

const $ = id => document.getElementById(id);

let currentUser = null;
let currentReviewId = null;

async function api(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || "Something went wrong.");
    }

    return data;
}

function message(id, text, type = "") {
    const element = $(id);
    if (!element) return;

    element.textContent = text;
    element.className = `message ${type}`;
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[char]);
}

function showApp(user) {
    currentUser = user;

    $("login-screen").hidden = true;
    $("app-screen").hidden = false;

    $("user-name").textContent = user.name;
    $("user-role").textContent = user.role;

    document.querySelectorAll(".admin-only").forEach(element => {
        element.hidden = user.role !== "admin";
    });

    document.querySelectorAll(".nav-btn").forEach(element => {
        const page = element.dataset.page;

        if (
            page === "audit" ||
            page === "analytics" ||
            page === "reviews"
        ) {
            element.hidden = user.role === "creator";
        }
    });

    loadDashboard();
    loadReviews();
    checkHealth();
}

async function login(email, password) {
    const result = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
    });

    showApp(result.user);
}

async function logout() {
    await api("/api/logout", { method: "POST" });

    currentUser = null;
    currentReviewId = null;

    $("app-screen").hidden = true;
    $("login-screen").hidden = false;
    $("login-form").reset();
}

async function checkHealth() {
    try {
        await api("/api/health");

        $("connection-status").textContent = "Connected";
        $("connection-status").classList.add("connected");
    } catch {
        $("connection-status").textContent = "Disconnected";
    }
}

/* NAVIGATION */

function navigate(page) {
    if (
        currentUser?.role === "creator" &&
        ["reviews", "analytics", "audit"].includes(page)
    ) {
        return;
    }

    if (
        currentUser?.role !== "admin" &&
        page === "guidelines"
    ) {
        return;
    }

    document.querySelectorAll(".page").forEach(element => {
        element.classList.toggle(
            "active",
            element.id === `page-${page}`
        );
    });

    document.querySelectorAll(".nav-btn").forEach(element => {
        element.classList.toggle(
            "active",
            element.dataset.page === page
        );
    });

    const headings = {
        dashboard: "Dashboard",
        analyzer: "Content Analyzer",
        reviews: "Team Reviews",
        analytics: "Analytics",
        guidelines: "Brand Guidelines",
        audit: "Audit Trail"
    };

    $("page-heading").textContent = headings[page] || "Dashboard";

    if (page === "reviews") loadReviews();
    if (page === "analytics") loadAnalytics();
    if (page === "audit") loadAudit();
    if (page === "guidelines") loadGuidelines();
}

function copyText(text) {
    navigator.clipboard.writeText(text)
        .then(() => alert("Copied successfully."))
        .catch(() => alert("Could not copy the text."));
}

/* ANALYSIS */

async function analyseContent() {
    const input = $("content-input");
    const button = $("analyze-button");
    const content = input.value.trim();

    if (!content) {
        message("analysis-status", "Please enter content to analyze.", "error");
        input.focus();
        return;
    }

    button.disabled = true;
    button.textContent = "Analyzing...";

    message("analysis-status", "Checking brand compliance...");

    try {
        const result = await api("/api/analyse", {
            method: "POST",
            body: JSON.stringify({ content })
        });

        currentReviewId = result.review_id;

        $("analysis-results").hidden = false;
        $("compliance-score").textContent =
            `${result.compliance_score}%`;

        $("score-summary").textContent = result.summary;

        renderFindings(result.findings || []);

        message(
            "analysis-status",
            "Analysis completed successfully.",
            "success"
        );

        loadDashboard();

    } catch (error) {
        message("analysis-status", error.message, "error");
    } finally {
        button.disabled = false;
        button.textContent = "Analyze content";
    }
}

function renderFindings(findings) {
    const container = $("findings-list");

    if (!findings.length) {
        container.innerHTML = `
            <div class="finding-card">
                <h4>No issues detected</h4>
                <p>Your content passed the configured checks.
                Human review is still recommended.</p>
            </div>`;
        return;
    }

    container.innerHTML = findings.map((finding, index) => `
        <div class="finding-card">
            <div class="finding-header">
                <h4>${escapeHTML(finding.title)}</h4>
                <span class="severity ${escapeHTML(finding.severity)}">
                    ${escapeHTML(finding.severity)}
                </span>
            </div>

            <p>${escapeHTML(finding.message)}</p>

            <div class="suggestion-box">
                <strong>Original:</strong>
                <p>${escapeHTML(finding.original)}</p>

                <strong>Suggested replacement:</strong>
                <p>${escapeHTML(finding.suggestion)}</p>

                <button class="secondary-btn copy-suggestion"
                    data-index="${index}">
                    Copy suggestion
                </button>

                <button class="secondary-btn apply-suggestion"
                    data-index="${index}">
                    Apply suggestion
                </button>
            </div>
        </div>
    `).join("");

    container.querySelectorAll(".copy-suggestion").forEach(button => {
        button.addEventListener("click", () => {
            copyText(findings[Number(button.dataset.index)].suggestion);
        });
    });

    container.querySelectorAll(".apply-suggestion").forEach(button => {
        button.addEventListener("click", () => {
            const finding = findings[Number(button.dataset.index)];
            const input = $("content-input");

            input.value = input.value.replace(
                finding.original,
                finding.suggestion
            );

            message(
                "analysis-status",
                "Suggestion applied. Analyze the updated content again.",
                "success"
            );
        });
    });
}

/* DASHBOARD */

async function loadDashboard() {
    try {
        const result = await api("/api/reviews");
        const reviews = result.reviews || [];

        const approved = reviews.filter(
            review => review.status === "approved"
        ).length;

        const pending = reviews.filter(
            review => ["pending", "in_review", "changes"]
                .includes(review.status)
        ).length;

        const average = reviews.length
            ? Math.round(
                reviews.reduce((sum, review) => sum + review.score, 0)
                / reviews.length
            )
            : 0;

        $("stat-total").textContent = reviews.length;
        $("stat-approved").textContent = approved;
        $("stat-pending").textContent = pending;
        $("stat-average").textContent = `${average}%`;

        $("dashboard-reviews").innerHTML = reviews.length
            ? reviews.slice(0, 5).map(review => `
                <div class="history-card">
                    <strong>Review #${review.id}</strong>
                    <p>${escapeHTML(review.content.slice(0, 120))}</p>
                    <small>
                        Score: ${review.score}% |
                        Status: ${escapeHTML(review.status)}
                    </small>
                </div>
            `).join("")
            : `<p class="empty-state">No reviews yet. Analyze your first content.</p>`;

    } catch (error) {
        console.error("Dashboard error:", error);
    }
}

/* REVIEWS */

async function loadReviews() {
    try {
        const result = await api("/api/reviews");
        const reviews = result.reviews || [];

        const container = $("reviews-list");

        if (!reviews.length) {
            container.innerHTML =
                `<p class="empty-state">No reviews available.</p>`;
            return;
        }

        container.innerHTML = reviews.map(review => `
            <div class="history-card">
                <div class="section-heading">
                    <strong>Review #${review.id}</strong>
                    <span class="review-status">
                        ${escapeHTML(review.status)}
                    </span>
                </div>

                <p>${escapeHTML(review.content.slice(0, 250))}</p>

                <small>
                    Creator: ${escapeHTML(review.creator_name)} |
                    Score: ${review.score}%
                </small>

                ${["admin", "reviewer"].includes(currentUser.role) ? `
                    <div class="review-actions">
                        <button class="approve"
                            data-id="${review.id}" data-decision="approved">
                            Approve
                        </button>
                        <button class="reject"
                            data-id="${review.id}" data-decision="rejected">
                            Reject
                        </button>
                        <button class="changes"
                            data-id="${review.id}" data-decision="changes">
                            Request changes
                        </button>
                        <button data-id="${review.id}"
                            data-decision="in_review">
                            In review
                        </button>
                    </div>
                ` : ""}
            </div>
        `).join("");

        container.querySelectorAll("[data-decision]").forEach(button => {
            button.addEventListener("click", () => {
                saveDecision(
                    button.dataset.id,
                    button.dataset.decision
                );
            });
        });

    } catch (error) {
        $("reviews-list").textContent = error.message;
    }
}

async function saveDecision(id, decision) {
    try {
        await api(`/api/reviews/${id}/decision`, {
            method: "POST",
            body: JSON.stringify({ decision })
        });

        alert("Review decision saved.");

        loadReviews();
        loadDashboard();

    } catch (error) {
        alert(error.message);
    }
}

/* ANALYTICS */

async function loadAnalytics() {
    try {
        const data = await api("/api/analytics");

        $("analytics-total").textContent = data.total_reviews;
        $("analytics-approved").textContent = data.approved;
        $("analytics-pending").textContent = data.pending;
        $("analytics-average").textContent =
            `${data.average_score}%`;

        const violations = Object.entries(data.violations || {});
        const maximum = Math.max(
            1,
            ...violations.map(item => item[1])
        );

        $("violations-list").innerHTML = violations.length
            ? violations.map(([name, count]) => `
                <div class="bar-row">
                    <div class="section-heading">
                        <span>${escapeHTML(name)}</span>
                        <strong>${count}</strong>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill"
                            style="width:${count / maximum * 100}%"></div>
                    </div>
                </div>
            `).join("")
            : `<p class="empty-state">No violations recorded yet.</p>`;

        $("trend-list").innerHTML = data.trend.length
            ? data.trend.map(item => `
                <div class="bar-row">
                    <div class="section-heading">
                        <span>${escapeHTML(item.created_at)}</span>
                        <strong>${Math.round(item.average_score)}%</strong>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill"
                            style="width:${item.average_score}%"></div>
                    </div>
                </div>
            `).join("")
            : `<p class="empty-state">No trend data available yet.</p>`;

    } catch (error) {
        console.error("Analytics error:", error);
    }
}

/* AUDIT TRAIL */

async function loadAudit() {
    try {
        const data = await api("/api/audit");

        $("audit-list").innerHTML = data.audit.length
            ? data.audit.map(item => `
                <div class="audit-card">
                    <strong>${escapeHTML(item.reviewer_name)}</strong>
                    <p>Review #${item.review_id} —
                        ${escapeHTML(item.action)}</p>
                    <small>${escapeHTML(item.created_at)}</small>
                </div>
            `).join("")
            : `<p class="empty-state">No review decisions recorded yet.</p>`;

    } catch (error) {
        $("audit-list").textContent = error.message;
    }
}

/* GUIDELINES */

async function loadGuidelines() {
    try {
        const data = await api("/api/guidelines");
        const g = data.guidelines;

        $("brand-name").value = g.brand_name;
        $("brand-tone").value = g.tone;
        $("approved-terms").value = g.approved_terms.join(", ");
        $("forbidden-terms").value = g.forbidden_terms.join(", ");
        $("required-terms").value = g.required_terms.join(", ");

    } catch (error) {
        message("guidelines-status", error.message, "error");
    }
}

async function saveGuidelines() {
    try {
        await api("/api/guidelines", {
            method: "POST",
            body: JSON.stringify({
                brand_name: $("brand-name").value,
                tone: $("brand-tone").value,
                approved_terms: $("approved-terms").value,
                forbidden_terms: $("forbidden-terms").value,
                required_terms: $("required-terms").value
            })
        });

        message(
            "guidelines-status",
            "Guidelines saved successfully.",
            "success"
        );

    } catch (error) {
        message("guidelines-status", error.message, "error");
    }
}

/* START APPLICATION */

document.addEventListener("DOMContentLoaded", async () => {

    $("login-form").addEventListener("submit", async event => {
        event.preventDefault();

        try {
            await login(
                $("login-email").value,
                $("login-password").value
            );
        } catch (error) {
            message("login-message", error.message, "error");
        }
    });

    document.querySelectorAll(".demo-account").forEach(button => {
        button.addEventListener("click", () => {
            $("login-email").value = button.dataset.email;
            $("login-password").value = button.dataset.password;
        });
    });

    $("logout-button").addEventListener("click", async () => {
        try {
            await logout();
        } catch (error) {
            alert(error.message);
        }
    });

    $("analyze-button").addEventListener("click", analyseContent);

    $("clear-button").addEventListener("click", () => {
        $("content-input").value = "";
        $("analysis-results").hidden = true;
        message("analysis-status", "");
        currentReviewId = null;
    });

    $("save-guidelines").addEventListener("click", saveGuidelines);

    $("refresh-reviews").addEventListener("click", loadReviews);

    document.querySelectorAll("[data-page]").forEach(button => {
        button.addEventListener("click", () => {
            navigate(button.dataset.page);
        });
    });

    document.querySelectorAll("[data-go]").forEach(button => {
        button.addEventListener("click", () => {
            navigate(button.dataset.go);
        });
    });

    try {
        const result = await api("/api/me");

        if (result.user) {
            showApp(result.user);
        }
    } catch (error) {
        console.error("Session check:", error);
    }
});