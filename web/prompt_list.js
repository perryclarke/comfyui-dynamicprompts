import { app } from "../../scripts/app.js";

// Saved prompt list for Random Prompts Advanced.
//
// The node's own "text" widget is hidden but kept: it always holds the open
// prompt, so the backend, IS_CHANGED and old workflows work unchanged.
// The full list lives in node.properties.dp_prompts and is saved with the workflow.

const NODE_TYPES = ["DPRandomGeneratorAdvanced"];
const PROP = "dp_prompts";

const STYLE = `
.dp-plist { display:flex; flex-direction:column; gap:4px; height:100%; box-sizing:border-box;
  font: 12px sans-serif; color: var(--input-text, #ddd); }
.dp-plist-rows { display:flex; flex-direction:column; gap:2px; flex:1; min-height:0; overflow-y:auto; }
.dp-plist-row { display:flex; align-items:center; gap:6px; padding:3px 6px; border-radius:4px; cursor:pointer;
  background: var(--comfy-input-bg, #222); border:1px solid var(--border-color, #444); flex:none; }
.dp-plist-row:hover { filter: brightness(1.2); }
.dp-plist-row.open { cursor:default; border-color: var(--p-primary-color, #4a8fdc); }
.dp-plist-chev { opacity:.7; width:10px; flex:none; }
.dp-plist-title { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.dp-plist-title.empty { opacity:.5; font-style:italic; }
.dp-plist-del { flex:none; border:none; background:none; color:inherit; cursor:pointer; opacity:.6; padding:0 2px; font-size:13px; }
.dp-plist-del:hover { opacity:1; }
.dp-plist-del:disabled { opacity:.2; cursor:default; }
.dp-plist-grip { flex:none; cursor:grab; opacity:.5; padding:0 2px; font-size:13px; user-select:none; touch-action:none; }
.dp-plist-grip:hover { opacity:1; }
.dp-plist-row.dragging { opacity:.5; }
.dp-plist.dragging, .dp-plist.dragging * { cursor:grabbing !important; user-select:none; }
.dp-plist-drop { flex:none; height:2px; margin:-2px 0; border-radius:1px; background: var(--p-primary-color, #4a8fdc); }
.dp-plist-text { flex:1 1 auto; min-height:80px; width:100%; box-sizing:border-box; resize:none;
  background: var(--comfy-input-bg, #222); color: var(--input-text, #ddd);
  border:1px solid var(--border-color, #444); border-radius:4px; padding:4px; font: 12px monospace; overflow-y:auto; }
.dp-plist-add { flex:none; align-self:flex-start; cursor:pointer; border-radius:4px; padding:2px 10px;
  background: var(--comfy-input-bg, #222); color: inherit; border:1px solid var(--border-color, #444); }
.dp-plist-add:hover { filter: brightness(1.2); }
.dp-plist-bar { flex:none; display:flex; align-items:center; gap:8px; }
.dp-plist-mode { margin-left:auto; display:flex; align-items:center; gap:4px; opacity:.85; }
.dp-plist-mode select { background: var(--comfy-input-bg, #222); color: inherit;
  border:1px solid var(--border-color, #444); border-radius:4px; font-size:12px; padding:1px 2px; }
`;

// What happens after a run is queued.
const MODES = [
    ["fixed", "stay on this prompt"],
    ["cycle", "go to next prompt"],
];

function injectStyle() {
    if (document.getElementById("dp-plist-style")) return;
    const s = document.createElement("style");
    s.id = "dp-plist-style";
    s.textContent = STYLE;
    document.head.appendChild(s);
}

function firstLine(text) {
    const line = (text || "").split("\n").find((l) => l.trim() !== "");
    return line ? line.trim() : "";
}

function setupPromptList(node) {
    const textWidget = node.widgets?.find((w) => w.name === "text");
    if (!textWidget || node._dpPromptList) return;
    injectStyle();

    textWidget.hidden = true;
    if (textWidget.options) textWidget.options.hidden = true;

    const container = document.createElement("div");
    container.className = "dp-plist";
    const rows = document.createElement("div");
    rows.className = "dp-plist-rows";
    const addBtn = document.createElement("button");
    addBtn.className = "dp-plist-add";
    addBtn.textContent = "+ New prompt";
    addBtn.title = "Add a new prompt";

    const modeWrap = document.createElement("label");
    modeWrap.className = "dp-plist-mode";
    modeWrap.title = "Queueing a run uses the open prompt. 'go to next prompt' then opens the next non-empty prompt, wrapping at the end, so queueing several runs steps through the list.";
    const modeSelect = document.createElement("select");
    for (const [value, label] of MODES) {
        const o = document.createElement("option");
        o.value = value;
        o.textContent = label;
        modeSelect.appendChild(o);
    }
    modeWrap.append("After each run:", modeSelect);

    const bar = document.createElement("div");
    bar.className = "dp-plist-bar";
    bar.append(addBtn, modeWrap);
    container.append(rows, bar);

    // Keep wheel scrolling inside the list/textarea instead of zooming the canvas.
    container.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });

    const state = {
        get data() {
            let d = node.properties?.[PROP];
            if (!d || !Array.isArray(d.prompts) || d.prompts.length === 0) {
                d = { version: 1, prompts: [textWidget.value ?? ""], active: 0 };
                node.properties = node.properties || {};
                node.properties[PROP] = d;
            }
            d.active = Math.min(Math.max(0, d.active | 0), d.prompts.length - 1);
            if (!MODES.some(([v]) => v === d.mode)) d.mode = "fixed";
            return d;
        },
    };

    function markChanged() {
        node.setDirtyCanvas?.(true, true);
        app.graph?.change?.();
    }

    function setText(value) {
        textWidget.value = value;
        textWidget.callback?.(value);
    }

    function activate(i) {
        const d = state.data;
        d.active = i;
        setText(d.prompts[i]);
        render(true);
        markChanged();
    }

    function remove(i) {
        const d = state.data;
        if (d.prompts.length <= 1) return;
        if (d.prompts[i].trim() !== "" && !confirm("Delete this prompt?\n\n" + firstLine(d.prompts[i]).slice(0, 120))) return;
        d.prompts.splice(i, 1);
        if (i < d.active || d.active >= d.prompts.length) d.active = Math.max(0, d.active - (i < d.active ? 1 : 0));
        d.active = Math.min(d.active, d.prompts.length - 1);
        setText(d.prompts[d.active]);
        render(false);
        markChanged();
    }

    modeSelect.addEventListener("change", () => {
        state.data.mode = modeSelect.value;
        markChanged();
    });
    // Keep canvas shortcuts and dragging from grabbing the select.
    modeSelect.addEventListener("pointerdown", (e) => e.stopPropagation());

    // Next non-empty prompt after the open one, wrapping; stays put if there is none.
    function advance() {
        const d = state.data;
        const n = d.prompts.length;
        for (let step = 1; step < n; step++) {
            const i = (d.active + step) % n;
            if (d.prompts[i].trim() !== "") {
                d.active = i;
                setText(d.prompts[i]);
                render(false);
                markChanged();
                return;
            }
        }
    }

    addBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const d = state.data;
        d.prompts.push("");
        activate(d.prompts.length - 1);
    });

    function makeDelete(i, count) {
        const del = document.createElement("button");
        del.className = "dp-plist-del";
        del.textContent = "🗑";
        del.title = count > 1 ? "Delete this prompt" : "The last prompt can't be deleted";
        del.disabled = count <= 1;
        del.addEventListener("click", (e) => { e.stopPropagation(); remove(i); });
        return del;
    }

    // Move prompt `from` so it ends up before the prompt currently at `to` (0..n).
    // The open prompt stays open, wherever it ends up.
    function move(from, to) {
        const d = state.data;
        const order = d.prompts.map((_, k) => k);
        const [item] = order.splice(from, 1);
        order.splice(to > from ? to - 1 : to, 0, item);
        d.prompts = order.map((k) => d.prompts[k]);
        d.active = order.indexOf(d.active);
        render(false);
        markChanged();
    }

    function startDrag(e, from, row) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const grip = e.currentTarget;
        grip.setPointerCapture(e.pointerId);
        row.classList.add("dragging");
        container.classList.add("dragging");
        const indicator = document.createElement("div");
        indicator.className = "dp-plist-drop";
        let target = null;

        const onMove = (ev) => {
            // Scroll the list when dragging near its top or bottom edge.
            const box = rows.getBoundingClientRect();
            if (ev.clientY < box.top + 16) rows.scrollTop -= 8;
            else if (ev.clientY > box.bottom - 16) rows.scrollTop += 8;

            const els = [...rows.querySelectorAll(".dp-plist-row")];
            let t = els.length;
            for (let k = 0; k < els.length; k++) {
                const b = els[k].getBoundingClientRect();
                if (ev.clientY < b.top + b.height / 2) { t = k; break; }
            }
            target = t === from || t === from + 1 ? null : t;
            if (target === null) indicator.remove();
            else if (target < els.length) rows.insertBefore(indicator, els[target]);
            else rows.appendChild(indicator);
        };
        const onEnd = (ev) => {
            grip.removeEventListener("pointermove", onMove);
            grip.removeEventListener("pointerup", onEnd);
            grip.removeEventListener("pointercancel", onEnd);
            if (grip.hasPointerCapture(e.pointerId)) grip.releasePointerCapture(e.pointerId);
            indicator.remove();
            row.classList.remove("dragging");
            container.classList.remove("dragging");
            if (ev.type === "pointerup" && target !== null) move(from, target);
        };
        grip.addEventListener("pointermove", onMove);
        grip.addEventListener("pointerup", onEnd);
        grip.addEventListener("pointercancel", onEnd);
    }

    function makeGrip(i, row) {
        const grip = document.createElement("span");
        grip.className = "dp-plist-grip";
        grip.textContent = "⠿";
        grip.title = "Drag to reorder. 'go to next prompt' runs the prompts in list order.";
        grip.addEventListener("pointerdown", (e) => startDrag(e, i, row));
        grip.addEventListener("click", (e) => e.stopPropagation());
        return grip;
    }

    function render(focus) {
        const d = state.data;
        modeSelect.value = d.mode;
        rows.replaceChildren();
        d.prompts.forEach((p, i) => {
            const row = document.createElement("div");
            row.className = "dp-plist-row" + (i === d.active ? " open" : "");
            const chev = document.createElement("span");
            chev.className = "dp-plist-chev";
            chev.textContent = i === d.active ? "▾" : "▸";
            const title = document.createElement("span");
            const fl = firstLine(p);
            title.className = "dp-plist-title" + (fl ? "" : " empty");
            title.textContent = fl || "(empty prompt)";
            title.title = fl;
            row.append(chev, title);
            if (d.prompts.length > 1) row.append(makeGrip(i, row));
            row.append(makeDelete(i, d.prompts.length));
            rows.appendChild(row);

            if (i === d.active) {
                const ta = document.createElement("textarea");
                ta.className = "dp-plist-text";
                ta.value = p;
                ta.placeholder = "Prompt (dynamic prompt syntax supported)";
                ta.spellcheck = false;
                ta.addEventListener("input", () => {
                    const dd = state.data;
                    dd.prompts[dd.active] = ta.value;
                    setText(ta.value);
                    const nfl = firstLine(ta.value);
                    title.textContent = nfl || "(empty prompt)";
                    title.className = "dp-plist-title" + (nfl ? "" : " empty");
                    title.title = nfl;
                    markChanged();
                });
                rows.appendChild(ta);
                if (focus) setTimeout(() => ta.focus(), 0);
            } else {
                row.addEventListener("click", (e) => { e.stopPropagation(); activate(i); });
            }
        });
    }

    const widget = node.addDOMWidget("prompt_list", "dp_prompt_list", container, {
        serialize: false,
        hideOnZoom: false,
        getMinHeight: () => 220,
    });
    widget.serialize = false;
    // Called by the frontend once per queued run, after the prompt has been sent.
    widget.afterQueued = () => {
        if (node.mode !== 0) return; // muted or bypassed
        if (state.data.mode === "cycle") advance();
    };

    node._dpPromptList = {
        // Called after a workflow is loaded: adopt saved list, or migrate the old single text.
        sync() {
            const saved = node.properties?.[PROP];
            if (!saved || !Array.isArray(saved.prompts) || saved.prompts.length === 0) {
                node.properties = node.properties || {};
                node.properties[PROP] = { version: 1, prompts: [textWidget.value ?? ""], active: 0 };
            } else {
                const d = state.data;
                // The text widget is what actually runs; if it was changed elsewhere, keep it.
                if ((textWidget.value ?? "") !== d.prompts[d.active]) d.prompts[d.active] = textWidget.value ?? "";
            }
            render(false);
        },
        render,
    };
    render(false);

    const sz = node.computeSize();
    node.setSize([Math.max(node.size[0], sz[0], 400), Math.max(node.size[1], sz[1])]);
}

app.registerExtension({
    name: "DP.PromptList",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_TYPES.includes(nodeData.name)) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            setupPromptList(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            // widgets_values are applied by now; let them settle, then sync the list.
            setTimeout(() => this._dpPromptList?.sync(), 0);
            return r;
        };
    },
});
