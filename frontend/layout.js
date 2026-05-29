const APP_NAV_ITEMS = [
    { label: "仪表盘", href: "dashboard.html" },
    { label: "AP课程库", href: "courses.html" },
    { label: "院校匹配", href: "match.html" },
    { label: "申请时间线", href: "timeline.html" },
    { label: "背景库", href: "portfolio.html" },
    { label: "AI规划", href: "ai-plan.html" },
    { label: "我的规划", href: "my-plans.html" },
    { label: "升学指南", href: "guide.html" },
    { label: "个人设置", href: "settings.html" }
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

    const displayName = user && user.name ? `${user.name}同学` : "学生中心";

    target.innerHTML = `
        <a class="app-logo" href="dashboard.html">AP Planner</a>
        <div class="app-nav-right">
            <span id="layout-user-name">${displayName}</span>
            <button class="app-logout-btn" onclick="logout()">退出登录</button>
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
