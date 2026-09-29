const HISTORY_TARGETS = new Set([
    "object-content",
    "substation-tab-content",
]);

document.addEventListener("htmx:beforeRequest", (event) => {
    const target = event.detail.target;

    if (!target || !HISTORY_TARGETS.has(target.id)) {
        return;
    }

    const history = target.querySelector("details.rzadb-otd-history");

    target.dataset.historyOpen = history?.open ? "true" : "false";
});

document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;

    if (!target || !HISTORY_TARGETS.has(target.id)) {
        return;
    }

    if (target.dataset.historyOpen !== "true") {
        return;
    }

    const history = target.querySelector("details.rzadb-otd-history");

    if (history) {
        history.open = true;
    }

    delete target.dataset.historyOpen;
});