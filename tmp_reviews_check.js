
    (function () {
        const wrap = document.getElementById("reviews-load-type-filter");
        const trigger = document.getElementById("reviews-select-trigger");
        const menu = document.getElementById("reviews-select-menu");
        const value = document.getElementById("reviews-select-value");
        const input = document.getElementById("reviews-select-input");
        const searchInput = document.getElementById("reviews-search-input");
        const searchIcon = document.querySelector(".reviews-search__icon");
        const filterWrap = document.getElementById("reviews-order-filter");
        const filterTrigger = document.getElementById("reviews-filter-trigger");
        const filterMenu = document.getElementById("reviews-filter-menu");
        const filterInput = document.getElementById("reviews-order-input");
        const filterValue = document.getElementById("reviews-filter-value");
        const periodWrap = document.getElementById("reviews-period-filter");
        const periodTrigger = document.getElementById("reviews-period-trigger");
        const periodMenu = document.getElementById("reviews-period-menu");
        const periodValue = document.getElementById("reviews-period-value");
        const periodInput = document.getElementById("reviews-period-input");
        const trainingViewModal = document.getElementById("reviews-training-view-modal");
        const trainingViewDate = document.getElementById("reviews-training-view-date");
        const trainingViewDirection = document.getElementById("reviews-training-view-direction");
        const trainingViewVisibility = document.getElementById("reviews-training-view-visibility");
        const trainingViewColorInput = document.getElementById("reviews-training-view-color-input");
        const trainingViewColorSelected = document.getElementById("reviews-training-view-color-selected");
        const trainingViewColorButtons = Array.from(document.querySelectorAll("[data-reviews-view-color]"));
        const trainingViewComment = document.getElementById("reviews-training-view-comment");
        const trainingViewName = document.getElementById("reviews-training-view-name");
        const trainingViewExisting = document.getElementById("reviews-training-view-existing");
        const trainingViewEditButton = document.getElementById("reviews-training-edit-btn");
        const trainingViewPayloadEl = document.getElementById("reviews-training-view-payload");
        const trainingViewPayload = trainingViewPayloadEl ? JSON.parse(trainingViewPayloadEl.textContent || "{}") : {};
        const calendarPageUrl = "{% url 'auth:calendar' %}";
        if (!wrap || !trigger || !menu || !value || !input) return;

        const params = new URLSearchParams(window.location.search);
        const labelsByPeriod = {
            all: "За всё время",
            today: "За сегодня",
            week: "За неделю",
            month: "За месяц"
        };
        const labelsByLoadType = {
            all: "Общая",
            cardio: "Кардио",
            metabolic: "Метаболическая",
            strength: "Силовая"
        };
        const labelsByOrder = {
            rating_desc: "По убыванию",
            rating_asc: "По возрастанию"
        };
        const PERIOD_STORAGE_KEY = "reviews_overview_selected_period";
        const PERIOD_VALUES = new Set(["all", "today", "week", "month"]);

        function normalizePeriodValue(value) {
            const normalized = String(value || "").trim().toLowerCase();
            return PERIOD_VALUES.has(normalized) ? normalized : "all";
        }

        function savePeriodToStorage(periodValue) {
            try {
                window.localStorage.setItem(PERIOD_STORAGE_KEY, normalizePeriodValue(periodValue));
            } catch (error) {
                console.warn("Cannot persist period filter", error);
            }
        }

        function loadPeriodFromStorage() {
            try {
                return normalizePeriodValue(window.localStorage.getItem(PERIOD_STORAGE_KEY));
            } catch (error) {
                console.warn("Cannot read persisted period filter", error);
                return "all";
            }
        }

        if (!params.has("period")) {
            const storedPeriod = loadPeriodFromStorage();
            if (storedPeriod !== "all") {
                params.set("period", storedPeriod);
                window.location.replace(`${window.location.pathname}?${params.toString()}`);
                return;
            }
        }

        const initialLoadType = (input.value || "all").toLowerCase();
        value.textContent = labelsByLoadType[initialLoadType] || "Общая";

        const options = menu.querySelectorAll(".reviews-select-menu__item");

        function setOpen(open) {
            trigger.setAttribute("aria-expanded", String(open));
            menu.hidden = !open;
            wrap.classList.toggle("is-open", open);
        }

        function escapeHtml(value) {
            return String(value || "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#39;");
        }

        function getTrainingColorAccent(colorKey) {
            const normalized = String(colorKey || "blue").trim().toLowerCase();
            if (normalized === "orange") return "#ffb86a";
            if (normalized === "green") return "#7bf1a8";
            if (normalized === "pink") return "#f9a8d4";
            if (normalized === "violet") return "#a5b4fc";
            return "#8ec5ff";
        }

        function getTrainingColorLabel(colorKey) {
            const normalized = String(colorKey || "blue").trim().toLowerCase();
            if (normalized === "orange") return "Оранжевый";
            if (normalized === "green") return "Зеленый";
            if (normalized === "pink") return "Розовый";
            if (normalized === "violet") return "Фиолетовый";
            return "Синий";
        }

        function renderTrainingColorView(colorKey) {
            const normalized = String(colorKey || "blue").trim().toLowerCase();
            if (trainingViewColorInput) {
                trainingViewColorInput.value = normalized;
            }
            if (trainingViewColorSelected) {
                trainingViewColorSelected.textContent = `Выбран цвет: ${getTrainingColorLabel(normalized)}`;
            }
            trainingViewColorButtons.forEach((button) => {
                const isActive = button.getAttribute("data-reviews-view-color") === normalized;
                button.classList.toggle("is-active", isActive);
                button.setAttribute("aria-pressed", isActive ? "true" : "false");
            });
        }

        function renderTrainingView(payload) {
            if (!payload || !trainingViewExisting) return;
            const color = String(payload.color || "blue").trim().toLowerCase();
            const accentColor = getTrainingColorAccent(color);
            const groups = new Map();
            (payload.exercises || []).forEach((item) => {
                const groupName = String(item.block || "Блок");
                if (!groups.has(groupName)) groups.set(groupName, []);
                groups.get(groupName).push(String(item.text || ""));
            });

            trainingViewExisting.innerHTML = Array.from(groups.entries()).map(([title, items]) => `
                <section class="calendar-create-modal__existing-group">
                    <h4 class="calendar-create-modal__existing-title">${escapeHtml(title)}</h4>
                    ${items.map((text) => `
                        <article class="calendar-create-modal__existing-item calendar-create-modal__existing-item--${escapeHtml(color)}" style="--exercise-accent:${escapeHtml(accentColor)};">
                            <span class="calendar-create-modal__existing-text">${escapeHtml(text)}</span>
                        </article>
                    `).join("")}
                </section>
            `).join("") || `<article class="calendar-create-modal__existing-item"><span class="calendar-create-modal__existing-text">Нет данных по упражнениям</span></article>`;
        }

        function openTrainingView(trainingKey) {
            if (!trainingViewModal) return;
            const payload = trainingViewPayload[trainingKey] || null;
            if (!payload) return;
            if (trainingViewDate) trainingViewDate.textContent = payload.date_label || "--";
            if (trainingViewDirection) trainingViewDirection.textContent = payload.direction || "--";
            if (trainingViewVisibility) trainingViewVisibility.textContent = payload.visibility || "--";
            renderTrainingColorView(payload.color || "blue");
            if (trainingViewComment) trainingViewComment.value = payload.comment || "";
            if (trainingViewName) trainingViewName.textContent = payload.title || "Тренировка";
            if (trainingViewEditButton) {
                const trainingId = Number(payload.training_id || 0);
                trainingViewEditButton.disabled = !trainingId;
                trainingViewEditButton.dataset.trainingId = trainingId ? String(trainingId) : "";
            }
            renderTrainingView(payload);
            trainingViewModal.hidden = false;
        }

        function closeTrainingView() {
            if (!trainingViewModal) return;
            trainingViewModal.hidden = true;
        }

        function applyFilters() {
            params.set("load_type", input.value || "all");
            params.set("order_by", filterInput?.value || "rating_desc");
            params.set("period", periodInput?.value || "all");
            const searchValue = (searchInput?.value || "").trim();
            if (searchValue) {
                params.set("q", searchValue);
            } else {
                params.delete("q");
            }
            window.location.search = params.toString();
        }

        trigger.addEventListener("click", function () {
            setOpen(menu.hidden);
        });

        options.forEach(function (option) {
            option.addEventListener("click", function () {
                const nextValue = option.getAttribute("data-load-type") || "all";
                const nextLabel = option.getAttribute("data-load-label") || "Общая";
                options.forEach(function (item) {
                    item.classList.remove("is-active");
                });
                option.classList.add("is-active");
                input.value = nextValue;
                value.textContent = nextLabel;
                setOpen(false);
                applyFilters();
            });
        });

        document.addEventListener("click", function (event) {
            if (!wrap.contains(event.target)) {
                setOpen(false);
            }
        });

        if (filterWrap && filterTrigger && filterMenu && filterInput) {
            const filterOptions = filterMenu.querySelectorAll(".reviews-select-menu__item");
            const initialOrder = (filterInput.value || "rating_desc").toLowerCase();
            if (filterValue) {
                filterValue.textContent = labelsByOrder[initialOrder] || labelsByOrder.rating_desc;
            }

            function setFilterOpen(open) {
                filterTrigger.setAttribute("aria-expanded", String(open));
                filterMenu.hidden = !open;
                filterWrap.classList.toggle("is-open", open);
            }

            filterTrigger.addEventListener("click", function () {
                setFilterOpen(filterMenu.hidden);
            });

            filterOptions.forEach(function (option) {
                option.addEventListener("click", function () {
                    const nextValue = option.getAttribute("data-order-value") || "rating_desc";
                    filterOptions.forEach(function (item) {
                        item.classList.remove("is-active");
                    });
                    option.classList.add("is-active");
                    filterInput.value = nextValue;
                    if (filterValue) {
                        filterValue.textContent = labelsByOrder[nextValue] || labelsByOrder.rating_desc;
                    }
                    setFilterOpen(false);
                    applyFilters();
                });
            });

            document.addEventListener("click", function (event) {
                if (!filterWrap.contains(event.target)) {
                    setFilterOpen(false);
                }
            });
        }

        if (periodWrap && periodTrigger && periodMenu && periodInput && periodValue) {
            const periodOptions = periodMenu.querySelectorAll(".reviews-select-menu__item");
            const initialPeriod = (periodInput.value || "all").toLowerCase();
            periodValue.textContent = labelsByPeriod[initialPeriod] || labelsByPeriod.all;
            savePeriodToStorage(initialPeriod);

            function setPeriodOpen(open) {
                periodTrigger.setAttribute("aria-expanded", String(open));
                periodMenu.hidden = !open;
                periodWrap.classList.toggle("is-open", open);
            }

            periodTrigger.addEventListener("click", function () {
                setPeriodOpen(periodMenu.hidden);
            });

            periodOptions.forEach(function (option) {
                option.addEventListener("click", function () {
                    const nextValue = option.getAttribute("data-period-value") || "all";
                    const nextLabel = option.getAttribute("data-period-label") || labelsByPeriod.all;
                    periodOptions.forEach(function (item) {
                        item.classList.remove("is-active");
                    });
                    option.classList.add("is-active");
                    periodInput.value = nextValue;
                    periodValue.textContent = nextLabel;
                    savePeriodToStorage(nextValue);
                    setPeriodOpen(false);
                    applyFilters();
                });
            });

            document.addEventListener("click", function (event) {
                if (!periodWrap.contains(event.target)) {
                    setPeriodOpen(false);
                }
            });
        }

        if (searchInput) {
            searchInput.addEventListener("keydown", function (event) {
                if (event.key !== "Enter") return;
                event.preventDefault();
                applyFilters();
            });
        }
        searchIcon?.addEventListener("click", function () {
            applyFilters();
        });

        document.addEventListener("click", function (event) {
            const openButton = event.target.closest("[data-open-training-view]");
            if (openButton) {
                const trainingKey = openButton.getAttribute("data-training-key") || "";
                if (trainingKey) {
                    openTrainingView(trainingKey);
                }
                return;
            }
            if (event.target.closest("[data-close-training-view]")) {
                closeTrainingView();
                return;
            }
            if (trainingViewEditButton && event.target.closest("#reviews-training-edit-btn")) {
                const trainingId = Number(trainingViewEditButton.dataset.trainingId || 0);
                if (trainingId) {
                    window.location.assign(`${calendarPageUrl}?edit_training_id=${trainingId}`);
                }
                return;
            }
            if (trainingViewModal && event.target === trainingViewModal) {
                closeTrainingView();
            }
        });
    })();

