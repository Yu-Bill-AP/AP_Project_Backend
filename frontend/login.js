(() => {
    const form = document.getElementById("login-form");
    const button = document.getElementById("login-btn");
    const username = document.getElementById("username");
    const password = document.getElementById("password");
    const errorMessage = document.getElementById("error-msg");
    const helpButton = document.getElementById("help-btn");
    const helpPanel = document.getElementById("help-panel");

    function fitScene() {
        const scale = Math.min(window.innerWidth / 1008, window.innerHeight / 720);
        document.documentElement.style.setProperty("--scene-scale", scale);
    }

    fitScene();
    window.addEventListener("resize", fitScene);

    if (new URLSearchParams(window.location.search).get("preview") !== "1") {
        redirectIfLoggedIn();
    }

    function closeHelp() {
        helpPanel.hidden = true;
        helpButton.setAttribute("aria-expanded", "false");
    }

    helpButton.addEventListener("click", () => {
        const open = helpPanel.hidden;
        helpPanel.hidden = !open;
        helpButton.setAttribute("aria-expanded", String(open));
    });

    document.addEventListener("click", event => {
        if (!helpPanel.hidden && !event.target.closest(".help-wrap")) closeHelp();
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !helpPanel.hidden) {
            closeHelp();
            helpButton.focus();
        }
    });

    for (const field of [username, password]) {
        field.addEventListener("input", () => { errorMessage.textContent = ""; });
    }

    function leavePage(destination) {
        form.inert = true;
        closeHelp();
        window.location.href = destination;
    }

    document.getElementById("register-link").addEventListener("click", event => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        leavePage("register.html");
    });

    function loginError(response, data) {
        if (response.status === 429) return "Too many attempts. Please try again shortly.";
        if (data.msg === "用户名不存在") return "Name not found.";
        if (data.msg === "密码错误") return "Incorrect password.";
        if (typeof data.msg === "string" && !/[\u3400-\u9fff]/.test(data.msg)) return data.msg;
        return "Unable to log in. Please try again.";
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (button.disabled) return;
        errorMessage.textContent = "";
        const name = username.value.trim();
        const secret = password.value.trim();

        if (!name || !secret) {
            errorMessage.textContent = "Please enter your name and password.";
            (!name ? username : password).focus();
            return;
        }

        button.disabled = true;
        button.setAttribute("aria-label", "Logging in");
        form.setAttribute("aria-busy", "true");

        try {
            const response = await fetch(AUTH_BASE_URL + "/api/login", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: name, password: secret })
            });
            const data = await response.json();

            if (!response.ok || data.code !== 200) {
                errorMessage.textContent = loginError(response, data);
                return;
            }

            // The server owns the HttpOnly session cookie.
            localStorage.removeItem("token");
            const status = await getOnboardingStatus(data.token);
            leavePage(status.requires_onboarding ? "profile.html" : "dashboard.html");
        } catch (error) {
            errorMessage.textContent = "Cannot connect. Please try again.";
        } finally {
            form.removeAttribute("aria-busy");
            if (!form.inert) {
                button.disabled = false;
                button.setAttribute("aria-label", "Log in");
            }
        }
    });
})();
