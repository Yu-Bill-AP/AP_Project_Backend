const AUTH_BASE_URL = window.location.origin;

function getToken() {
    return localStorage.getItem("token") || "";
}

function authHeaders(token = getToken()) {
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

function clearAuth() {
    localStorage.removeItem("token");
    localStorage.removeItem("userInfo");
    localStorage.removeItem("profileData");
}

function redirectToLogin() {
    window.location.href = "login.html";
}

function getCurrentPage() {
    return window.location.pathname.split("/").pop() || "dashboard.html";
}

function isProfilePage() {
    return getCurrentPage() === "profile.html";
}

async function getOnboardingStatus(token) {
    try {
        const response = await fetch(`${AUTH_BASE_URL}/api/onboarding/status`, {
            credentials: "same-origin",
            headers: authHeaders(token)
        });
        const data = await response.json();

        if (data.code !== 200) {
            return { completed: false, requires_onboarding: true };
        }

        return data.data;
    } catch (error) {
        return { completed: false, requires_onboarding: true };
    }
}

async function verifyToken() {
    const token = getToken();

    try {
        const response = await fetch(`${AUTH_BASE_URL}/api/user/info`, {
            credentials: "same-origin",
            headers: authHeaders(token)
        });
        const data = await response.json();

        if (data.code !== 200) {
            clearAuth();
            return null;
        }

        localStorage.setItem("userInfo", JSON.stringify(data.data));
        return {
            token,
            user: data.data
        };
    } catch (error) {
        clearAuth();
        return null;
    }
}

async function requireLogin(onVerified, options = {}) {
    const auth = await verifyToken();

    if (!auth) {
        redirectToLogin();
        return;
    }

    const shouldRequireProfile = options.requireProfile !== false && !isProfilePage();
    if (shouldRequireProfile) {
        const status = await getOnboardingStatus(auth.token);
        if (status.requires_onboarding) {
            window.location.href = "profile.html";
            return;
        }
    }

    if (typeof onVerified === "function") {
        await onVerified(auth.user, auth.token);
    }
}

async function redirectIfLoggedIn() {
    const auth = await verifyToken();

    if (auth) {
        const status = await getOnboardingStatus(auth.token);
        window.location.href = status.requires_onboarding ? "profile.html" : "dashboard.html";
    }
}

async function logout() {
    try {
        await fetch(`${AUTH_BASE_URL}/api/logout`, {
            method: "POST",
            credentials: "same-origin"
        });
    } catch (error) {
        // 即使服务暂不可达，也要清理浏览器中的旧凭证。
    }
    clearAuth();
    redirectToLogin();
}

function escapeHtml(text) {
    return String(text || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
