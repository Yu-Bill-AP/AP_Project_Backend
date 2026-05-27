const AUTH_BASE_URL = "http://127.0.0.1:8000";

function getToken() {
    return localStorage.getItem("token");
}

function clearAuth() {
    localStorage.removeItem("token");
    localStorage.removeItem("userInfo");
    localStorage.removeItem("profileData");
}

function redirectToLogin() {
    window.location.href = "login.html";
}

async function verifyToken() {
    const token = getToken();

    if (!token) {
        return null;
    }

    try {
        const response = await fetch(`${AUTH_BASE_URL}/api/user/info`, {
            headers: {
                "Authorization": `Bearer ${token}`
            }
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

async function requireLogin(onVerified) {
    const auth = await verifyToken();

    if (!auth) {
        redirectToLogin();
        return;
    }

    if (typeof onVerified === "function") {
        await onVerified(auth.user, auth.token);
    }
}

async function redirectIfLoggedIn() {
    const auth = await verifyToken();

    if (auth) {
        window.location.href = "dashboard.html";
    }
}

function logout() {
    clearAuth();
    redirectToLogin();
}
