(function () {
    const storageKey = "rzadb-theme";
    const root = document.documentElement;
    const toggle = document.getElementById("theme-toggle");
    const icon = document.getElementById("theme-icon");

    function getSystemTheme() {
        return window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
    }

    function applyTheme(theme) {
        root.setAttribute("data-bs-theme", theme);

        if (icon) {
            icon.textContent = theme === "dark"
                ? "light_mode"
                : "dark_mode";
        }
    }

    const savedTheme = localStorage.getItem(storageKey);
    const initialTheme = savedTheme || getSystemTheme();

    applyTheme(initialTheme);

    if (toggle) {
        toggle.addEventListener("click", function () {
            const currentTheme =
                root.getAttribute("data-bs-theme") || "light";

            const newTheme =
                currentTheme === "dark" ? "light" : "dark";

            localStorage.setItem(storageKey, newTheme);
            applyTheme(newTheme);
        });
    }
})();