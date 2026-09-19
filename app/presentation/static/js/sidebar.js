(() => {
    const sidebar = document.getElementById("app-sidebar");
    const resizer = document.getElementById("sidebar-resizer");
    const collapseButton = document.getElementById("sidebar-collapse");

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