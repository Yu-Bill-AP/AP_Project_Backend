const APP_NAV_ITEMS = [
    { label: "Dashboard", href: "dashboard.html" },
    { label: "Profile", href: "profile.html" },
    { label: "AP Courses", href: "courses.html" },
    { label: "Matches", href: "match.html" },
    { label: "Timeline", href: "timeline.html" },
    { label: "Portfolio", href: "portfolio.html" },
    { label: "AI Planner", href: "ai-plan.html" },
    { label: "Saved Plans", href: "my-plans.html" },
    { label: "Guide", href: "guide.html" },
    { label: "Settings", href: "settings.html" }
];

function getCurrentPageName() {
    const page = window.location.pathname.split("/").pop();
    return page || "dashboard.html";
}

function renderTopbar(user) {
    const target = document.getElementById("app-topbar");

    if (!target) {
        return;
    }

    const displayName = user && user.name ? `${escapeHtml(user.name)}` : "Student";

    target.innerHTML = `
        <a class="app-logo" href="dashboard.html"><img class="app-wordmark" src="assets/login/title.png" alt="AP Planner" width="164" height="35"><img class="app-cat" src="assets/login/cat.png" alt="" width="39" height="37"></a>
        <div class="app-nav-right">
            <span id="layout-user-name">${displayName}</span>
            <button class="app-logout-btn" onclick="logout()">Log out</button>
        </div>
    `;
}

function renderSidebar() {
    const target = document.getElementById("app-sidebar");

    if (!target) {
        return;
    }

    const currentPage = getCurrentPageName();
    const links = APP_NAV_ITEMS.map(item => {
        const activeClass = item.href === currentPage ? " active" : "";
        return `<a class="app-sidebar-link${activeClass}" href="${item.href}">${item.label}</a>`;
    }).join("");

    target.innerHTML = `<nav class="app-sidebar-nav">${links}</nav>`;
}

function renderAppLayout(user) {
    renderTopbar(user);
    renderSidebar();
}

// Draw the shared shell immediately; account data fills in after verification.
renderTopbar();
renderSidebar();
