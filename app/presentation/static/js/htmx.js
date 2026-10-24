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

document.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.detail.target;

    if (
        event.detail.xhr.status === 409 &&
        target?.id === "archive-preview-modal-body"
    ) {
        event.detail.shouldSwap = true;
        event.detail.isError = false;
    }
});


document.addEventListener("htmx:beforeRequest", () => {
    const message = document.getElementById("htmx-error-message");

    if (message) {
        message.classList.add("d-none");
    }
});

document.addEventListener("htmx:responseError", (event) => {
    const target = event.detail.target;
    const isArchiveModalBody =
        target?.id?.startsWith("archive-") && target.id.endsWith("-modal-body");

    // Ошибки валидации остальных форм обрабатываются их существующими паттернами.
    if (event.detail.xhr.status === 422 && !isArchiveModalBody) {
        return;
    }

    if (isArchiveModalBody) {
        let errorText = "Доступ запрещён или объект не найден.";
        try {
            const response = JSON.parse(event.detail.xhr.response);
            if (typeof response.detail === "string") {
                errorText = response.detail;
            } else if (event.detail.xhr.status === 422) {
                errorText = "Укажите обязательную причину архивирования.";
            }
        } catch {
            // Используем понятное сообщение, если сервер вернул не JSON.
        }
        const alert = document.createElement("div");
        alert.className = "alert alert-danger mb-0";
        alert.setAttribute("role", "alert");
        alert.textContent = errorText;
        target.replaceChildren(alert);
        return;
    }

    const message = document.getElementById("htmx-error-message");
    const text = document.getElementById("htmx-error-text");

    if (!message || !text) {
        return;
    }

    let errorText = "Не удалось выполнить операцию. Попробуйте ещё раз.";

    try {
        const response = JSON.parse(event.detail.xhr.response);

        if (typeof response.detail === "string") {
            errorText = response.detail;
        }
    } catch {
        // Ответ не является JSON — используем общее сообщение.
    }

    text.textContent = errorText;
    message.classList.remove("d-none");
});
