
    (function () {
        window.addEventListener("pageshow", (event) => {
            let mustRefresh = false;
            try {
                mustRefresh = window.sessionStorage.getItem("achievements_refresh_required") === "1";
            } catch (_error) {
                mustRefresh = false;
            }
            if (!mustRefresh) return;
            try {
                window.sessionStorage.removeItem("achievements_refresh_required");
            } catch (_error) {}
            if (event.persisted) {
                window.location.reload();
            }
        });

        const tabs = document.querySelectorAll("[data-achievements-tab]");
        const panels = document.querySelectorAll("[data-achievements-panel]");

        function activateTab(tabName) {
            tabs.forEach((tab) => {
                tab.classList.toggle("achievements-tabs__item--active", tab.dataset.achievementsTab === tabName);
            });
            panels.forEach((panel) => {
                panel.hidden = panel.dataset.achievementsPanel !== tabName;
            });
        }

        const benchTabs = document.querySelectorAll("[data-bench-tab]");
        const benchPanels = document.querySelectorAll("[data-bench-panel]");

        function activateBenchTab(tabName) {
            benchTabs.forEach((tab) => {
                tab.classList.toggle("achievements-bench-tabs__item--active", tab.dataset.benchTab === tabName);
            });
            benchPanels.forEach((panel) => {
                panel.hidden = panel.dataset.benchPanel !== tabName;
            });
        }

        tabs.forEach((tab) => {
            tab.addEventListener("click", () => activateTab(tab.dataset.achievementsTab));
        });

        benchTabs.forEach((tab) => {
            tab.addEventListener("click", () => activateBenchTab(tab.dataset.benchTab));
        });

        activateBenchTab("girls");
    })();

