document.addEventListener("click", (event) => {
    const tab = event.target.closest(".nav-tabs .nav-link");

    if (!tab || tab.disabled) {
        return;
    }

    const tabList = tab.closest(".nav-tabs");

    if (!tabList) {
        return;
    }

    tabList
        .querySelectorAll(".nav-link")
        .forEach((item) => item.classList.remove("active"));

    tab.classList.add("active");
});

document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(window.location.search);
    const requestedTab = params.get("tab");

    if (!requestedTab) {
        return;
    }

    const tab = document.querySelector(
        `[data-rzadb-tabs] [data-rzadb-tab][data-tab="${requestedTab}"]`
    );

    if (tab && !tab.disabled) {
        tab.click();
    }
});