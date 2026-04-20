
    (function () {
        const updateUrl = "{{ exercise_update_url }}";
        const openButton = document.getElementById("exercise-open-edit-modal");
        const modal = document.getElementById("exercise-edit-modal");
        const calculateButton = document.getElementById("exercise-edit-save");
        const persistButton = document.getElementById("exercise-save-db");
        const errorNode = document.getElementById("exercise-edit-error");
        const inputs = {
            rep_1: document.getElementById("exercise-edit-rep-1"),
            rep_2: document.getElementById("exercise-edit-rep-2"),
            rep_3: document.getElementById("exercise-edit-rep-3"),
            rep_4: document.getElementById("exercise-edit-rep-4"),
        };
        const maxValueNodes = Array.from(document.querySelectorAll("[data-max-rep-value]"));
        const percentRows = Array.from(document.querySelectorAll("[data-percent-row]"));
        const repTabs = Array.from(document.querySelectorAll("[data-rep-tab]"));
        let activeRepTabIndex = 0;

        const initialRepsNode = document.getElementById("exercise-initial-reps-json");
        const initialPercentsNode = document.getElementById("exercise-relative-percents-json");
        const state = {
            reps: initialRepsNode?.textContent ? JSON.parse(initialRepsNode.textContent) : { rep_1: 10, rep_2: 10, rep_3: 10, rep_4: 10 },
            percents: initialPercentsNode?.textContent ? JSON.parse(initialPercentsNode.textContent) : { p1: 100, p2: 100, p3: 100, p4: 100 },
        };

        function getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length !== 2) return "";
            return parts.pop().split(";").shift();
        }

        function normalizePositiveInt(value) {
            const parsed = Number.parseInt(String(value || "").trim(), 10);
            if (!Number.isFinite(parsed) || parsed < 1) return null;
            return parsed;
        }

        function setModalVisible(visible) {
            modal.hidden = !visible;
            document.body.style.overflow = visible ? "hidden" : "";
        }

        function getRepsArray() {
            return [
                Number(state.reps.rep_1) || 0,
                Number(state.reps.rep_2) || 0,
                Number(state.reps.rep_3) || 0,
                Number(state.reps.rep_4) || 0,
            ];
        }

        function getPercentMatrix() {
            return percentRows.map((rowNode) => {
                const percentNodesInRow = Array.from(rowNode.querySelectorAll(".exercise-percent-row__cell span"));
                return percentNodesInRow.map((node) => {
                    const raw = String(node.textContent || "").replace("%", "").trim();
                    const parsed = Number.parseInt(raw, 10);
                    return Number.isFinite(parsed) ? parsed : 0;
                });
            });
        }

        function renderPercentTableForActiveRep() {
            const reps = getRepsArray();
            const baseRep = reps[activeRepTabIndex] || 0;
            const matrix = getPercentMatrix();
            percentRows.forEach((rowNode, rowIndex) => {
                const valueNodes = Array.from(rowNode.querySelectorAll("[data-percent-value]"));
                const rowPercents = matrix[rowIndex] || [];
                valueNodes.forEach((valueNode, colIndex) => {
                    const percentValue = rowPercents[colIndex] || 0;
                    valueNode.textContent = String(Math.round((baseRep * percentValue) / 100));
                });
            });
        }

        function setActiveRepTab(index) {
            activeRepTabIndex = index;
            repTabs.forEach((tab, tabIndex) => {
                tab.classList.toggle("exercise-percent-head__item--active", tabIndex === index);
            });
            renderPercentTableForActiveRep();
        }

        function fillInputsFromState() {
            inputs.rep_1.value = String(state.reps.rep_1 ?? "");
            inputs.rep_2.value = String(state.reps.rep_2 ?? "");
            inputs.rep_3.value = String(state.reps.rep_3 ?? "");
            inputs.rep_4.value = String(state.reps.rep_4 ?? "");
        }

        function syncMaxRepValues() {
            const repValues = [state.reps.rep_1, state.reps.rep_2, state.reps.rep_3, state.reps.rep_4];
            maxValueNodes.forEach((node, index) => {
                if (repValues[index] !== undefined && repValues[index] !== null) {
                    node.textContent = String(repValues[index]);
                }
            });
        }

        function applySavedData(data) {
            const reps = data?.reps || {};
            state.reps = {
                rep_1: reps.rep_1,
                rep_2: reps.rep_2,
                rep_3: reps.rep_3,
                rep_4: reps.rep_4,
            };
            state.percents = data?.relative_percents || state.percents;
            syncMaxRepValues();

            const rows = data?.percent_rows || [];
            percentRows.forEach((rowNode, rowIndex) => {
                const cells = Array.from(rowNode.querySelectorAll("[data-percent-value]"));
                const rowData = rows[rowIndex] || [];
                cells.forEach((cellNode, colIndex) => {
                    const value = rowData[colIndex]?.value;
                    if (value !== undefined && value !== null) {
                        cellNode.textContent = String(value);
                    }
                });
            });
            renderPercentTableForActiveRep();
        }

        function collectPayloadFromInputs() {
            return {
                rep_1: normalizePositiveInt(inputs.rep_1.value),
                rep_2: normalizePositiveInt(inputs.rep_2.value),
                rep_3: normalizePositiveInt(inputs.rep_3.value),
                rep_4: normalizePositiveInt(inputs.rep_4.value),
            };
        }

        function collectPayloadFromState() {
            return {
                rep_1: normalizePositiveInt(state.reps.rep_1),
                rep_2: normalizePositiveInt(state.reps.rep_2),
                rep_3: normalizePositiveInt(state.reps.rep_3),
                rep_4: normalizePositiveInt(state.reps.rep_4),
            };
        }

        function calculateRepsLocally() {
            const payload = collectPayloadFromInputs();
            if (Object.values(payload).some((value) => value === null)) {
                errorNode.textContent = "Enter 4 positive numbers.";
                errorNode.hidden = false;
                return;
            }

            errorNode.hidden = true;
            state.reps = {
                rep_1: payload.rep_1,
                rep_2: payload.rep_2,
                rep_3: payload.rep_3,
                rep_4: payload.rep_4,
            };
            syncMaxRepValues();
            renderPercentTableForActiveRep();
            setModalVisible(false);
        }

        async function persistRepsToDb() {
            const payload = collectPayloadFromState();
            if (Object.values(payload).some((value) => value === null)) {
                window.alert("РќРµРІРµСЂРЅС‹Рµ Р·РЅР°С‡РµРЅРёСЏ. РќР°Р¶РјРёС‚Рµ 'РџРѕСЃС‡РёС‚Р°С‚СЊ', Р·Р°С‚РµРј 'РЎРѕС…СЂР°РЅРёС‚СЊ'.");
                return;
            }

            const initialButtonText = persistButton.textContent;
            persistButton.disabled = true;
            persistButton.textContent = "РЎРѕС…СЂР°РЅРµРЅРёРµ...";
            try {
                const response = await fetch(updateUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCookie("csrftoken"),
                    },
                    body: JSON.stringify(payload),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.ok) {
                    window.alert("РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ. РџСЂРѕРІРµСЂСЊС‚Рµ Р·РЅР°С‡РµРЅРёСЏ Рё РїРѕРїСЂРѕР±СѓР№С‚Рµ РµС‰Рµ СЂР°Р·.");
                    return;
                }
                applySavedData(data);
                try {
                    window.sessionStorage.setItem("achievements_refresh_required", "1");
                } catch (_error) {}
                persistButton.textContent = "РЎРѕС…СЂР°РЅРµРЅРѕ";
                window.setTimeout(() => {
                    persistButton.textContent = initialButtonText;
                }, 1200);
            } catch (error) {
                window.alert("РћС€РёР±РєР° СЃРµС‚Рё РїСЂРё СЃРѕС…СЂР°РЅРµРЅРёРё. РџРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР°.");
            } finally {
                persistButton.disabled = false;
                if (persistButton.textContent !== "РЎРѕС…СЂР°РЅРµРЅРѕ") {
                    persistButton.textContent = initialButtonText;
                }
            }
        }
        openButton?.addEventListener("click", () => {
            errorNode.hidden = true;
            fillInputsFromState();
            setModalVisible(true);
        });

        calculateButton?.addEventListener("click", calculateRepsLocally);
        persistButton?.addEventListener("click", persistRepsToDb);

        modal?.querySelectorAll("[data-close-edit-modal]").forEach((node) => {
            node.addEventListener("click", () => setModalVisible(false));
        });

        repTabs.forEach((tab, index) => {
            tab.addEventListener("click", () => setActiveRepTab(index));
            tab.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                setActiveRepTab(index);
            });
        });

        setActiveRepTab(0);
    })();

