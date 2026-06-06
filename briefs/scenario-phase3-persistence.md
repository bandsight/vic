# Scenario Panel Phase 3 — Override Persistence & Save-and-Note

## ⚠️ SCOPE CONSTRAINTS
- MAY touch: `main.py`, `static/app.js`, `static/style.css`
- MAY create: `scenario-overrides/` directory (at project root, i.e. `ROOT / "scenario-overrides"`)
- MUST NOT touch: any file in `canonical/`, `src/`, `tests/`, `registers/`, `data/`
- MUST NOT run any pipeline scripts or extraction scripts
- If you hit an ambiguity or unexpected state, STOP and report. Do not attempt workarounds.

## Setup
```bash
cd /home/john/.openclaw/workspace/projects/eba-workbench
source .venv/bin/activate
python -m pytest tests/scenario_testing/ -q   # must show 37 passed before you start
./node_modules/.bin/eslint static/app.js       # must show 0 errors before you start
```

## Context

`main.py` is a FastAPI server (port 8765) serving a human-in-loop EBA extraction workbench.
`static/app.js` is an ES module loaded via `<script type="module">`.
The scenario panel lives in the "Uplift rules" tab. It calls:
  `POST /api/councils/{ae_id}/uplift-rules/scenarios` with body `{ overrides: {...} }` to render results.
Cell-level overrides are held in `const scenarioOverrides = new Map()` in `app.js` (line 36) — currently in-memory only, lost on refresh.
`ROOT = Path(__file__).parent` in `main.py` (line 22); `CANONICAL_DIR = ROOT / "canonical"` (line 27).

The task is to persist overrides to disk per-council and add a "Save & note" workflow.

## Tasks

### 1. Create `scenario-overrides/` directory placeholder
```bash
mkdir -p scenario-overrides
touch scenario-overrides/.gitkeep
```

### 2. Add four backend endpoints to `main.py`

Add these after the existing `POST /api/councils/{ae_id}/uplift-rules/scenarios` route.
Define `SCENARIO_OVERRIDES_DIR = ROOT / "scenario-overrides"` near the top of main.py alongside the other path constants.

**Endpoint A — GET saved state**
```
GET /api/councils/{ae_id}/uplift-rules/scenarios/overrides
```
Reads `scenario-overrides/{ae_id}.json` if it exists.
Returns:
```json
{ "ae_id": "ae527870", "overrides": {...}, "notes": "...", "saved_at": "2026-04-21T09:31:00+10:00" }
```
If file does not exist returns:
```json
{ "ae_id": "ae527870", "overrides": {}, "notes": null, "saved_at": null }
```

**Endpoint B — POST auto-save overrides**
```
POST /api/councils/{ae_id}/uplift-rules/scenarios/overrides
Body: { "overrides": {...} }
```
Reads existing file if present (to preserve existing `notes` and `saved_at`).
Writes `scenario-overrides/{ae_id}.json` with:
- `ae_id`, `overrides` (from request body)
- `notes` preserved from existing file (or null if new)
- `saved_at` = current UTC ISO timestamp
If the overrides dict is empty, delete the file if it exists (and return `{ ae_id, overrides: {}, notes: null, saved_at: null }`).
Returns: `{ "ae_id": "...", "saved_at": "..." }`

**Endpoint C — POST save note**
```
POST /api/councils/{ae_id}/uplift-rules/scenarios/note
Body: { "notes": "..." }
```
Reads existing file. Updates `notes` field. Writes back.
If no file exists yet, creates one with `overrides: {}`.
Returns: `{ "ae_id": "...", "saved_at": "..." }`

**Endpoint D — DELETE saved state**
```
DELETE /api/councils/{ae_id}/uplift-rules/scenarios/overrides
```
Deletes `scenario-overrides/{ae_id}.json` if it exists.
Returns: `{ "ae_id": "...", "cleared": true }`

All four endpoints should return HTTP 200. Use `datetime.now(timezone.utc).isoformat()` for timestamps.
File I/O: read/write with `json.loads` / `json.dumps(indent=2)`, UTF-8.

### 3. Frontend changes to `static/app.js`

**3a. Restore saved overrides on council load**

In the function that handles council selection (currently calls `loadUpliftScenarios(council.agreement_id)` at line 1015), BEFORE calling `loadUpliftScenarios`, fetch saved overrides and populate the Map:

```js
async function restoreScenarioOverrides(ae_id) {
  try {
    const saved = await api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/overrides`);
    if (saved.overrides && Object.keys(saved.overrides).length) {
      scenarioOverrides.set(ae_id, saved.overrides);
    }
    return saved; // { overrides, notes, saved_at }
  } catch (_) {
    return { overrides: {}, notes: null, saved_at: null };
  }
}
```

Call this before `loadUpliftScenarios` in the council-selection handler.

**3b. Auto-save on every override action**

At the end of `applyScenarioOverride` (line 1262), after calling `loadUpliftScenarios(ae_id)`, add a fire-and-forget auto-save:

```js
// Auto-save overrides (fire-and-forget; errors logged to console only)
const overridesForCouncil = scenarioOverrides.get(ae_id) || {};
api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/overrides`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ overrides: overridesForCouncil }),
}).then((resp) => {
  updateScenarioSavedBadge(ae_id, resp.saved_at);
}).catch((err) => console.warn("auto-save failed:", err));
```

**3c. Add saved badge + "Save & note" + "Clear" to the scenario panel header**

In `renderUpliftScenarios` (line 1298), add to the panel header HTML:

- A `<span id="scenario-saved-badge" class="scenario-saved-badge"></span>` that shows e.g. `💾 Saved 09:31` when overrides are saved (empty/hidden when no saved state)
- A `<button id="scenario-save-note-btn" class="scenario-save-note-btn">Save & note</button>` — visible only when `scenarioOverrides.get(ae_id)` has entries
- A `<button id="scenario-clear-btn" class="scenario-clear-btn">Clear overrides</button>` — visible only when badge shows saved state

The saved badge initial text should be set from `window._scenarioSavedAt` (a module-level variable you'll set after restoring on load). Implement:

```js
let _scenarioSavedAt = null; // module-level, tracks last saved_at for current council

function updateScenarioSavedBadge(ae_id, saved_at) {
  _scenarioSavedAt = saved_at;
  const badge = document.getElementById("scenario-saved-badge");
  if (!badge) return;
  if (saved_at) {
    const t = new Date(saved_at);
    const hhmm = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    badge.textContent = `💾 Saved ${hhmm}`;
    badge.style.display = "";
  } else {
    badge.textContent = "";
    badge.style.display = "none";
  }
}
```

**3d. "Save & note" modal**

When the "Save & note" button is clicked (use the delegated listener pattern already in the file — `document.addEventListener("click", ...)`), open a modal with:
- A read-only auto-generated summary (see format below)
- A `<textarea>` for human comment (placeholder: "Add your reasoning here…")
- "Save note" button and "Cancel" button

Auto-generate the summary from the current `scenarioOverrides.get(ae_id)` map:
- For each period, for each cell key:
  - `action: "use_computed"` → `"Used computed for {band}:{level} ({period}) → {weekly}."`
  - `action: "accept"` → `"Accepted {band}:{level} ({period}) as-is."`
  - `action: "deleted"` → `"Deleted {band}:{level} ({period})."`
- Join with `" "`, then append `"\n---\n"` separator before the textarea value.

On "Save note": POST `{ notes: summary + "\n---\n" + humanComment }` to the note endpoint. Close modal. Update badge.

Implement the modal as a `<dialog>` element appended to `document.body` (standard HTML dialog, no external libraries).

**3e. "Clear overrides" button**

On click: confirm with `window.confirm("Clear all saved overrides for this council?")`. If confirmed, call `DELETE /api/councils/{ae_id}/uplift-rules/scenarios/overrides`, clear `scenarioOverrides.delete(ae_id)`, update badge to hidden, reload scenarios via `loadUpliftScenarios(ae_id)`.

### 4. CSS additions to `static/style.css`

Add styles for:
- `.scenario-saved-badge` — small muted text, `font-size: 0.75rem`, `color: var(--muted, #888)`, inline-block, margin-left auto in the header flex row
- `.scenario-save-note-btn` — subtle button, similar to existing secondary buttons in the file
- `.scenario-clear-btn` — small, muted/danger-adjacent, `color: #c00` or similar
- `dialog.scenario-note-dialog` — centered modal, `max-width: 480px`, standard dialog padding, backdrop via `::backdrop { background: rgba(0,0,0,0.4) }`
- `dialog.scenario-note-dialog textarea` — `width: 100%`, `min-height: 80px`, `box-sizing: border-box`
- `dialog.scenario-note-dialog .dialog-summary` — `font-size: 0.8rem`, `color: var(--muted, #888)`, `background: #f5f5f5`, `padding: 0.5rem`, `border-radius: 4px`, `margin-bottom: 0.75rem`, `white-space: pre-wrap`

### 5. Verification
```bash
# All tests still pass
python -m pytest tests/scenario_testing/ -q

# ESLint 0 errors
./node_modules/.bin/eslint static/app.js

# Server starts without import errors
python -c "from main import app; print('OK')"

# Directory exists
ls -la scenario-overrides/.gitkeep

# Smoke-test endpoints
curl -s http://localhost:8765/api/councils/ae527870/uplift-rules/scenarios/overrides | python -m json.tool
curl -s -X POST http://localhost:8765/api/councils/ae527870/uplift-rules/scenarios/overrides \
  -H "Content-Type: application/json" \
  -d '{"overrides":{"2025-07-12":{"7:A":{"action":"use_computed","weekly":2073.36}}}}' | python -m json.tool
ls scenario-overrides/ae527870.json
curl -s http://localhost:8765/api/councils/ae527870/uplift-rules/scenarios/overrides | python -m json.tool
curl -s -X DELETE http://localhost:8765/api/councils/ae527870/uplift-rules/scenarios/overrides | python -m json.tool
```

## Expected output
- `scenario-overrides/.gitkeep` — empty placeholder
- `main.py` — 4 new endpoints (GET/POST/POST/DELETE) under `/api/councils/{ae_id}/uplift-rules/scenarios/overrides` and `/note`; `SCENARIO_OVERRIDES_DIR` constant defined
- `static/app.js` — `restoreScenarioOverrides`, `updateScenarioSavedBadge`, modal logic, auto-save in `applyScenarioOverride`, delegated handlers for save-note and clear buttons; `_scenarioSavedAt` module-level var
- `static/style.css` — styles for badge, buttons, dialog

## Commit
```bash
cd /home/john/.openclaw/workspace
git add -f \
  projects/eba-workbench/scenario-overrides/.gitkeep \
  projects/eba-workbench/main.py \
  projects/eba-workbench/static/app.js \
  projects/eba-workbench/static/style.css
git commit -m "scenario panel: Phase 3 override persistence and Save & note

- SCENARIO_OVERRIDES_DIR = ROOT / 'scenario-overrides'
- GET /…/scenarios/overrides — returns saved state (overrides + notes + saved_at)
- POST /…/scenarios/overrides — auto-save overrides; deletes file when overrides empty
- POST /…/scenarios/note — update notes on saved state
- DELETE /…/scenarios/overrides — clear saved state
- Frontend: restoreScenarioOverrides() on council load; auto-save on every
  applyScenarioOverride(); saved badge (💾 Saved HH:MM); Save & note modal
  (<dialog>, auto-populated summary + human comment textarea); Clear overrides
  button with confirmation; delegated click handlers throughout"
```
