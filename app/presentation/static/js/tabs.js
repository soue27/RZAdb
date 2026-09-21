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