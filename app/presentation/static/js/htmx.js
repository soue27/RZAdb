document.addEventListener("htmx:beforeRequest", (event) => {
    const target = event.detail.target;

    if (!target || target.id !== "object-content") {
        return;
    }

    const history = target.querySelector("details.rzadb-otd-history");

    target.dataset.otdHistoryOpen = history?.open ? "true" : "false";
});

document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;

    if (!target || target.id !== "object-content") {
        return;
    }

    if (target.dataset.otdHistoryOpen !== "true") {
        return;
    }

    const history = target.querySelector("details.rzadb-otd-history");

    if (history) {
        history.open = true;
    }

    delete target.dataset.otdHistoryOpen;
});