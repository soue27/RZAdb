(() => {
    const sidebar = document.getElementById("app-sidebar");
    const resizer = document.getElementById("sidebar-resizer");
    const collapseButton = document.getElementById("sidebar-collapse");
    const searchForm = document.getElementById("sidebar-search-form");
    const searchInput = document.getElementById("sidebar-search-input");

    if (!sidebar || !resizer || !collapseButton) {
        return;
    }

    const MIN_WIDTH = 280;
    const MAX_WIDTH = 520;

    const STORAGE_WIDTH = "rzadb-sidebar-width";
    const STORAGE_COLLAPSED = "rzadb-sidebar-collapsed";

    let isResizing = false;
    let expandedWidth = sidebar.getBoundingClientRect().width;


    /*
     * Storage
     */

    function saveWidth() {
        localStorage.setItem(
            STORAGE_WIDTH,
            String(expandedWidth),
        );
    }


    function loadWidth() {
        const savedWidth = Number(
            localStorage.getItem(STORAGE_WIDTH),
        );

        if (
            Number.isFinite(savedWidth)
            && savedWidth >= MIN_WIDTH
            && savedWidth <= MAX_WIDTH
        ) {
            expandedWidth = savedWidth;
        }
    }


    function saveCollapsedState(isCollapsed) {
        localStorage.setItem(
            STORAGE_COLLAPSED,
            String(isCollapsed),
        );
    }


    function loadCollapsedState() {
        return localStorage.getItem(STORAGE_COLLAPSED) === "true";
    }


    /*
     * UI state
     */

    function updateCollapseButton() {
        const isCollapsed = sidebar.classList.contains(
            "is-collapsed",
        );

        if (isCollapsed) {
            collapseButton.title = "Развернуть панель";
            collapseButton.setAttribute(
                "aria-label",
                "Развернуть панель",
            );
        } else {
            collapseButton.title = "Свернуть панель";
            collapseButton.setAttribute(
                "aria-label",
                "Свернуть панель",
            );
        }
    }


    function collapseSidebar() {
        /*
         * Remember current width before collapsing.
         */
        expandedWidth = sidebar.getBoundingClientRect().width;

        saveWidth();

        sidebar.classList.add("is-collapsed");

        /*
         * Remove inline dimensions so CSS
         * `.is-collapsed` can set width/flex-basis to 0.
         */
        sidebar.style.width = "";
        sidebar.style.flexBasis = "";

        saveCollapsedState(true);

        updateCollapseButton();
    }


    function expandSidebar() {
        /*
         * Restore the last expanded width.
         */
        loadWidth();

        sidebar.classList.remove("is-collapsed");

        sidebar.style.width = `${expandedWidth}px`;
        sidebar.style.flexBasis = `${expandedWidth}px`;

        saveCollapsedState(false);

        updateCollapseButton();
    }


    /*
     * Restore saved state
     */

    loadWidth();

    if (loadCollapsedState()) {
        sidebar.classList.add("is-collapsed");

        sidebar.style.width = "";
        sidebar.style.flexBasis = "";
    } else {
        sidebar.style.width = `${expandedWidth}px`;
        sidebar.style.flexBasis = `${expandedWidth}px`;
    }

    updateCollapseButton();

    if (searchForm) {
        sidebar.addEventListener("click", (event) => {
            const clickedToggle = event.target.closest("#sidebar-archive-toggle");
            if (!clickedToggle) {
                return;
            }
            document.getElementById("sidebar-search-results").innerHTML = "";
            sidebar.querySelectorAll(".search-selected").forEach((item) => item.classList.remove("search-selected"));
            const archiveMode = searchForm.elements.archive_only;
            const enabled = archiveMode.value !== "true";
            archiveMode.value = String(enabled);
            clickedToggle.setAttribute("aria-pressed", String(enabled));
            htmx.trigger(document.body, "refresh-tree");
        });
        searchInput?.addEventListener("input", () => {
            sidebar.querySelectorAll(".search-selected").forEach((item) => item.classList.remove("search-selected"));
        });

        sidebar.addEventListener("click", (event) => {
            const result = event.target.closest("[data-search-result]");
            if (!result) return;

            sidebar.querySelectorAll(".search-selected").forEach((item) => {
                item.classList.remove("search-selected");
            });

            const pathIds = result.dataset.pathIds.split(",");
            pathIds.slice(0, -1).forEach((id) => {
                const node = sidebar.querySelector(`[data-tree-node-id="${id}"]`);
                const children = node?.querySelector(":scope > .collapse");
                children?.classList.add("show");
                node?.querySelector(":scope > .tree-row > .tree-expand-button")?.setAttribute("aria-expanded", "true");
            });

            const objectType = result.dataset.objectType;
            const targetId = result.dataset.objectId;
            const targetNode = sidebar.querySelector(`[data-tree-node-id="${targetId}"]`);
            if (objectType === "enterprise" && result.dataset.hasCard === "true") {
                const treeItem = sidebar.querySelector(`[data-object-id="${targetId}"]`);
                treeItem?.classList.add("search-selected");
                treeItem?.click();
                treeItem?.scrollIntoView({block: "nearest"});
            } else if (objectType === "enterprise") {
                targetNode?.querySelectorAll(".collapse").forEach((element) => {
                    element.classList.add("show");
                });
                targetNode?.querySelectorAll(".tree-expand-button").forEach((button) => {
                    button.setAttribute("aria-expanded", "true");
                });
                const enterpriseItem = targetNode?.querySelector(":scope > .tree-row > .tree-item");
                enterpriseItem?.classList.add("search-selected");
                enterpriseItem?.scrollIntoView({block: "nearest"});
            } else {
                const treeItem = sidebar.querySelector(`[data-object-id="${targetId}"]`);
                treeItem?.classList.add("search-selected");
                treeItem?.click();
                treeItem?.scrollIntoView({block: "nearest"});
            }
        });

        document.body.addEventListener("htmx:beforeRequest", (event) => {
            if (event.detail.elt?.id !== "sidebar-load-more") return;
            document.getElementById("sidebar-search-error")?.remove();
        });

        document.body.addEventListener("htmx:responseError", (event) => {
            const source = event.detail.elt;
            const target = event.detail.target;
            if (
                source?.id === "sidebar-search-form"
                && target?.id === "sidebar-search-results"
            ) {
                const results = document.getElementById("sidebar-search-results");
                if (results) {
                    results.innerHTML = '<div class="small text-danger py-2">Не удалось выполнить поиск. Попробуйте ещё раз.</div>';
                }
                event.stopPropagation();
                return;
            }

            if (
                source?.id !== "sidebar-load-more"
                || target?.id !== "sidebar-search-results-list"
            ) {
                return;
            }

            const resultList = document.getElementById("sidebar-search-results-list");
            if (!resultList) return;

            const message = document.createElement("div");
            message.id = "sidebar-search-error";
            message.className = "small text-danger py-2";
            message.setAttribute("role", "alert");
            message.textContent = "Не удалось загрузить следующие результаты. Нажмите «Загрузить ещё», чтобы повторить.";
            resultList.insertAdjacentElement("afterend", message);
            event.stopPropagation();
        });
    }


    /*
     * Resize
     */

    resizer.addEventListener("mousedown", (event) => {
        if (sidebar.classList.contains("is-collapsed")) {
            return;
        }

        isResizing = true;

        expandedWidth = sidebar.getBoundingClientRect().width;

        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";

        event.preventDefault();
    });


    document.addEventListener("mousemove", (event) => {
        if (!isResizing) {
            return;
        }

        const newWidth = Math.min(
            MAX_WIDTH,
            Math.max(MIN_WIDTH, event.clientX),
        );

        expandedWidth = newWidth;

        sidebar.style.width = `${newWidth}px`;
        sidebar.style.flexBasis = `${newWidth}px`;
    });


    document.addEventListener("mouseup", () => {
        if (!isResizing) {
            return;
        }

        isResizing = false;

        document.body.style.cursor = "";
        document.body.style.userSelect = "";

        saveWidth();
    });


    /*
     * Collapse / expand
     */

    collapseButton.addEventListener("click", () => {
        const isCollapsed = sidebar.classList.contains(
            "is-collapsed",
        );

        if (isCollapsed) {
            expandSidebar();
        } else {
            collapseSidebar();
        }
    });
})();
