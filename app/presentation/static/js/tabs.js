document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-rzadb-tab]");

    if (!tab) {
        return;
    }

    const tabsContainer = tab.closest("[data-rzadb-tabs]");

    if (!tabsContainer) {
        return;
    }

    tabsContainer
        .querySelectorAll("[data-rzadb-tab]")
        .forEach((item) => {
            item.classList.remove("active");
        });

    tab.classList.add("active");
});