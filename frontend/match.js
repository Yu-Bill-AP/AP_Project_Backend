let schoolMatches = [];
let matchToken = "";
let matchRequest = null;
let matchesLoading = false;

const matchElement = id => document.getElementById(id);
const matchEscape = value => escapeHtml(value == null ? "" : String(value));
const englishPolicyText = {
    not_required: "A separate English test is not required.",
    recommended: "English testing is recommended for some applicants.",
    required_when_no_english_medium: "English proof is required unless an approved exemption or alternative applies.",
    required_for_international: "English tests are requested from applicants without U.S. citizenship or permanent residence. Published scores are reference levels, not minimums.",
    cycle_check: "Current English requirements still need verification."
};

function safeUrl(url) {
    try {
        const parsed = new URL(String(url));
        return parsed.protocol === "https:" ? parsed.href : "#";
    } catch { return "#"; }
}

function renderSignals(signals) {
    matchElement("signal-major").textContent = signals.majorTrack || "Undecided";
    matchElement("signal-gpa").textContent = (signals.gpa || {}).label || "Not recorded";
    const test = signals.standardizedTest || {};
    const sources = { official: "official", mock: "mock", estimated: "estimated", planned: "planned" };
    matchElement("signal-sat").textContent = test.score != null ?
        `${test.type} ${test.score} · ${sources[test.source] || "official"}` : "Not recorded";
    matchElement("signal-language").textContent = (signals.language || {}).label || "Not recorded";
    matchElement("signal-ap").textContent = `${signals.apCount || 0} recorded · ${signals.apCompletedCount || 0} completed`;
}

function sourceLinks(sources) {
    const labels = {
        application: "Application", international: "International / English",
        testing: "Testing policy", english: "English tests", recommendations: "Recommendations",
        materials: "Materials", deadlines: "Deadlines", englishMethods: "English proof options",
        englishPolicyDetails: "English policy details", testingDetails: "Testing details",
        englishCatalog: "Undergraduate catalog"
    };
    const seen = new Set();
    return Object.entries(sources || {}).map(([key, value]) => {
        const url = safeUrl(value);
        if (url === "#" || seen.has(url)) return "";
        seen.add(url);
        return `<a class="source-link" href="${matchEscape(url)}" target="_blank" rel="noopener noreferrer">${matchEscape(labels[key] || "Official source")} ↗</a>`;
    }).join("");
}

function renderMatches() {
    if (matchesLoading) return;
    const query = matchElement("match-search").value.trim().toLocaleLowerCase();
    const policyFilter = matchElement("match-policy").value;
    const checkFilter = matchElement("match-check").value;
    const limit = Number(matchElement("match-limit").value);
    const filtered = schoolMatches.filter(item => {
        const policies = item.officialPolicies || {};
        const checks = item.requirementChecks || [];
        const hasBlocker = checks.some(check => check.severity === "blocker");
        const pending = (item.requirementsToCheck || []).length ||
            checks.some(check => check.severity === "warning") ||
            (item.officialReview || {}).status !== "reviewed";
        const text = `${item.school} ${item.location}`.toLocaleLowerCase();
        const policyMatches = !policyFilter || policies.testPolicyKey === policyFilter ||
            (policyFilter === "conditional_sat_act" && policies.catalogTestPolicyKey === "conditional_sat_act") ||
            (policyFilter === "program_dependent" && policies.catalogTestPolicyKey === "program_dependent");
        return (!query || text.includes(query)) && policyMatches &&
            (!checkFilter || (checkFilter === "blocker" && hasBlocker) ||
                (checkFilter === "followup" && pending) || (checkFilter === "no_blocker" && !hasBlocker));
    });
    const results = filtered.slice(0, limit);
    const openSchools = new Set([...document.querySelectorAll(".school-details[open]")].map(node => node.dataset.school));
    matchElement("match-count").textContent = `${results.length} shown · ${filtered.length} match your filters · ${schoolMatches.length} universities`;
    matchElement("school-list").innerHTML = results.length ? results.map(item => {
        const policies = item.officialPolicies || {};
        const gates = item.requirementsToCheck || [];
        const gaps = item.academicGaps || [];
        const checks = item.requirementChecks || [];
        const blockers = checks.filter(check => check.severity === "blocker");
        const warnings = checks.filter(check => check.severity === "warning");
        const review = item.officialReview || {};
        const reviewPending = (review.pendingFields || []).length > 0;
        const conflicts = item.officialSourceConflicts || [];
        const alert = blockers.length ?
            `<div class="requirement-alert">${matchEscape(blockers[0].title)}. Review the requirement details before building your list.</div>` :
            conflicts.length ? '<div class="requirement-alert warning">Official pages differ on a requirement. Review the source notes below.</div>' :
            (warnings.length || gates.length || reviewPending) ?
                '<div class="requirement-alert warning">Some requirements or profile evidence still need checking. Open the details below.</div>' : "";
        const checkMarkup = checks.length ?
            `<ul class="check-list">${checks.map(check => `<li><span class="check-state ${matchEscape(check.severity)}">${check.severity === "blocker" ? "Gap" : check.severity === "warning" ? "Review" : "On file"}</span><span><strong>${matchEscape(check.title)}</strong><br>${matchEscape(check.detail)}</span></li>`).join("")}</ul>` :
            "<p>These requirements have not been verified against your profile yet.</p>";
        const englishKey = review.pendingFields?.includes("english") || item.entryYear !== review.entryYear ?
            "cycle_check" : policies.englishPolicyKey;
        return `<article class="school-card ${blockers.length ? "blocked" : ""}">
            <div class="school-top">
                <div><h2>${matchEscape(item.school)}</h2><div class="school-subtitle">${matchEscape(item.location)} · Research band ${matchEscape(item.usNewsRankBand)}</div></div>
                <div class="fit"><strong>${matchEscape(item.fitScore)}</strong><span>Planning fit</span></div>
            </div>
            <div class="tag-row">
                <span class="tag">${matchEscape(item.recommendationBand)}</span>
                <span class="tag">Major fit ${matchEscape(item.majorStrength)}/100</span>
                ${blockers.length ? `<span class="tag gate">${blockers.length} requirement gaps</span>` : `<span class="tag">${warnings.length + gates.length} items to review</span>`}
                <span class="tag ${reviewPending ? "warning" : ""}">${reviewPending ? "Official review incomplete" : "Policy sources checked"}</span>
                ${conflicts.length ? '<span class="tag warning">Official sources differ</span>' : ""}
            </div>
            <p class="review-note">Sources read ${matchEscape(review.checkedAt || item.lastReviewed)} · Fall ${matchEscape(review.entryYear || 2027)} baseline</p>
            ${alert}
            <div class="policy-preview">
                <div><h3>SAT / ACT</h3><p>${matchEscape(policies.test)}</p></div>
                <div><h3>English proficiency</h3><p>${matchEscape(englishPolicyText[englishKey] || policies.english)}</p></div>
            </div>
            <details class="school-details" data-school="${matchEscape(item.school)}" ${openSchools.has(item.school) ? "open" : ""}>
                <summary>Requirements &amp; your profile</summary>
                <div class="school-grid">
                    <div class="detail"><h3>Testing details</h3><p>${matchEscape(policies.testPolicyNote)}${(policies.policyFlags || []).length ? `<br>${matchEscape(policies.policyFlags.join("；"))}` : ""}</p></div>
                    <div class="detail"><h3>English test details</h3><p>${matchEscape(policies.englishRequirementNote || policies.english)}</p></div>
                    <div class="detail"><h3>Application &amp; deadlines</h3><p>${matchEscape(policies.applicationSystem)}。${matchEscape(policies.deadlineNote)}</p></div>
                    <div class="detail"><h3>Application checklist</h3><ul>${(policies.requirements || []).map(value => `<li>${matchEscape(value)}</li>`).join("")}</ul></div>
                    <div class="detail"><h3>Your requirement checks</h3>${checkMarkup}</div>
                    <div class="detail"><h3>Preparation &amp; next steps</h3>${gates.length || gaps.length ? `<ul class="gap-list">${[...gates, ...gaps].map(value => `<li>${matchEscape(value)}</li>`).join("")}</ul>` : "<p>No additional gaps were identified in the recorded fields. This is not a complete admissions eligibility decision.</p>"}</div>
                    <div class="detail"><h3>Major fit</h3><p>${matchEscape(item.majorReason)}</p></div>
                    <div class="detail"><h3>International financial aid</h3><p>${matchEscape(policies.financialAidInternational)}</p></div>
                    ${reviewPending ? `<div class="detail"><h3>Official review still pending</h3><p>${matchEscape(review.pendingFields.join(", "))}。${matchEscape(review.note)}</p></div>` : ""}
                    ${conflicts.length ? `<div class="detail"><h3>Official source differences</h3>${conflicts.map(conflict => `<p><strong>${matchEscape(conflict.title)}</strong><br>${matchEscape(conflict.detail)}</p>`).join("")}</div>` : ""}
                </div>
            </details>
            <div class="source-row" aria-label="Official university sources">${sourceLinks(item.officialSources)}</div>
        </article>`;
    }).join("") : '<div class="empty">No universities match these filters.</div>';
}

async function loadMatches() {
    if (matchRequest) matchRequest.abort();
    const request = new AbortController();
    matchRequest = request;
    matchesLoading = true;
    matchElement("school-list").setAttribute("aria-busy", "true");
    matchElement("match-count").textContent = "Loading requirements...";
    schoolMatches = [];
    try {
        const year = matchElement("match-entry-year").value;
        const response = await fetch(`${AUTH_BASE_URL}/api/school-matches?entry_year=${encodeURIComponent(year)}`, {
            credentials: "same-origin", headers: authHeaders(matchToken), signal: request.signal
        });
        const result = await response.json();
        if (!response.ok || result.code !== 200) throw new Error(result.msg || "Unable to load university matches.");
        if (request !== matchRequest) return;
        const data = result.data;
        schoolMatches = data.matches || [];
        renderSignals(data.profileSignals || {});
        const coverage = data.reviewCoverage || {};
        matchElement("scope-note").textContent = `${schoolMatches.length} U.S. universities · Fall ${data.entryYear} entry · Official sources checked ${coverage.checkedAt || ""}`;
        matchElement("review-coverage").textContent = `${coverage.reviewedSchools || 0} of ${coverage.attemptedSchools || schoolMatches.length} testing and English reviews complete. ${(coverage.pendingSchools || []).length} school(s) still have unverified fields; ${(coverage.sourceConflictSchools || []).length} have conflicting official guidance. See each checklist for details.`;
        matchElement("disclaimer").textContent = "Official requirements and internal planning signals are shown separately. Planning fit is not an admission probability. Use the entry year and official links when comparing policies.";
        matchesLoading = false;
        renderMatches();
    } catch (error) {
        if (error.name === "AbortError" || request !== matchRequest) return;
        matchesLoading = false;
        matchElement("match-count").textContent = "Unable to load matches.";
        matchElement("school-list").innerHTML = `<div class="empty">${matchEscape(error.message)}</div>`;
    } finally {
        if (request === matchRequest) {
            matchesLoading = false;
            matchElement("school-list").setAttribute("aria-busy", "false");
        }
    }
}

matchElement("match-search").addEventListener("input", renderMatches);
for (const id of ["match-limit", "match-policy", "match-check"]) {
    matchElement(id).addEventListener("change", renderMatches);
}
matchElement("match-entry-year").addEventListener("change", loadMatches);
requireLogin(async (user, token) => {
    matchToken = token;
    renderAppLayout(user);
    await loadMatches();
});
