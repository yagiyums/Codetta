(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const editor = $("#sourceEditor");
  const syncStatus = $("#syncStatus");
  const diagnosticBar = $("#diagnosticBar");
  const diagnosticText = $("#diagnosticText");
  const grid = $("#editorGrid");
  let state = null;
  let mode = "python";
  let revision = 0;
  let latestApplied = 0;
  let timer = null;
  let zoom = 1;
  let selectedEvent = null;
  let sourceVisible = true;
  let debug = false;
  let syncing = false;
  let currentTool = "select";
  let toolAnchor = null;
  let savedJson = "";
  const drafts = {python: null, json: null};
  const invalid = {python: false, json: false};
  const stale = {python: false, json: false};
  const undoStack = [];
  const redoStack = [];

  function icon(name) { return `<svg><use href="#i-${name}"/></svg>`; }
  function setStatus(kind, message) {
    syncStatus.className = `status-primary ${kind === "invalid" ? "invalid" : kind === "checking" ? "checking" : kind === "stale" ? "stale" : ""}`;
    syncStatus.innerHTML = `${icon(kind === "invalid" ? "error" : kind === "synced" ? "check" : "info")}<span>${message}</span>`;
    $(".sync-dot").style.background = kind === "invalid" ? "var(--danger)" : kind === "synced" ? "var(--green)" : "var(--accent-2)";
  }

  function setDiagnostic(message, error = false) {
    diagnosticBar.classList.toggle("error", error);
    diagnosticBar.querySelector("use").setAttribute("href", error ? "#i-error" : "#i-info");
    diagnosticText.textContent = message;
    $("#problemsStatus span").textContent = error ? "1" : "0";
  }

  function toast(title, detail = "") {
    const item = document.createElement("div");
    item.className = "toast";
    item.innerHTML = `<strong></strong><span></span>`;
    item.querySelector("strong").textContent = title;
    item.querySelector("span").textContent = detail;
    $("#toasts").append(item);
    setTimeout(() => item.remove(), 3600);
  }

  function lineNumbers() {
    const count = Math.max(1, editor.value.split("\n").length);
    $("#lineNumbers").textContent = Array.from({length: count}, (_, index) => index + 1).join("\n");
  }

  function bodyScore() { return state.score.score; }
  function allEvents() {
    const items = [];
    bodyScore().parts.forEach(part => part.staves.forEach((staff, staffIndex) =>
      staff.measures.forEach(measure => measure.voices.forEach((voice, voiceIndex) =>
        voice.events.forEach(event => items.push({event, staff: staffIndex + 1, voice: voiceIndex + 1, measure: measure.number}))
      ))));
    return items;
  }

  function fractionText(value) {
    if (!value) return "";
    return value.d === 1 ? String(value.n) : `${value.n}/${value.d}`;
  }

  function pitchText(event) {
    if (event.type === "rest") return "Rest";
    const pitch = event.pitch || event.pitches?.[0];
    const accidental = pitch.alter === 1 ? "♯" : pitch.alter === -1 ? "♭" : pitch.alter === 2 ? "𝄪" : pitch.alter === -2 ? "𝄫" : "";
    return `${pitch.step}${accidental}${pitch.octave}`;
  }

  function renderEventList() {
    const list = $("#eventList");
    list.replaceChildren();
    allEvents().forEach(({event, staff}) => {
      const button = document.createElement("button");
      button.className = `event-card ${event.type === "rest" ? "rest" : ""} ${event.id === selectedEvent ? "active" : ""}`;
      button.dataset.event = event.id;
      button.title = `${event.id} · Staff ${staff} · duration ${fractionText(event.duration)}`;
      button.innerHTML = `<span>${event.type === "rest" ? "𝄽" : "♩"} ${pitchText(event)}</span><small>S${staff}</small>`;
      button.addEventListener("click", () => currentTool === "select" ? selectEvent(event.id) : applyNotationTool(event.id));
      list.append(button);
    });
  }

  function selectEvent(id) {
    selectedEvent = id;
    renderEventList();
    const found = allEvents().find(item => item.event.id === id);
    if (!found) return;
    const event = found.event;
    $("#inspectorEmpty").hidden = event.type !== "rest";
    $("#inspectorFields").hidden = event.type === "rest";
    if (event.type === "rest") {
      $("#inspectorEmpty").textContent = `Rest ${id} · duration ${fractionText(event.duration)}`;
      return;
    }
    const pitch = event.pitch || event.pitches[0];
    $("#eventId").textContent = id;
    $("#pitchStep").value = pitch.step;
    $("#pitchOctave").value = pitch.octave;
    $("#accidental").value = event.accidental || (pitch.alter === 1 ? "sharp" : pitch.alter === -1 ? "flat" : "");
    $("#stem").value = event.stem || "";
    const duration = `${event.duration.n}/${event.duration.d}`;
    const durationSelect = $("#eventDuration");
    if (![...durationSelect.options].some(option => option.value === duration)) {
      const option = new Option(`Custom (${fractionText(event.duration)})`, duration);
      durationSelect.add(option);
    }
    durationSelect.value = duration;
    const tied = bodyScore().spanners.some(spanner => spanner.type === "tie" && (spanner.start_anchor === id || spanner.end_anchor === id));
    durationSelect.disabled = tied;
    $("#inspectorHint").textContent = tied
      ? "This note belongs to a tie chain. Edit its value in Python so Composer can respell the complete chain safely."
      : "Pitch changes preserve the result; duration changes update the program after validation.";
  }

  function renderState(next, {keepEditor = false} = {}) {
    state = next;
    latestApplied = Math.max(latestApplied, next.revision || 0);
    $("#scoreSvg").innerHTML = debug ? next.debug_svg : next.svg;
    $("#renderLoading").style.display = "none";
    $("#resultStatus strong").textContent = next.result;
    $("#documentTitle").textContent = next.title;
    $("#staffMeta").textContent = `${next.staff_count} ${next.staff_count === 1 ? "staff" : "staves"}`;
    const filename = `${next.title.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "untitled"}.codetta`;
    $("#commandTitle").textContent = filename;
    $("#tabTitle").textContent = filename;
    $("#scoreFile span").textContent = filename;
    document.title = `${next.title} — Codetta Composer`;
    if (!keepEditor) editor.value = drafts[mode] ?? next[mode];
    lineNumbers();
    renderEventList();
    if (selectedEvent) selectEvent(selectedEvent);
    document.body.classList.toggle("dirty", Boolean(savedJson && next.json !== savedJson));
  }

  async function request(path, payload) {
    const response = await fetch(path, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw Object.assign(new Error(result.error || "Composer request failed"), {revision: result.revision});
    return result;
  }

  async function syncDraft(source, sourceMode, {history = true, keepEditor = true} = {}) {
    const ownRevision = ++revision;
    syncing = true;
    setStatus("checking", "Checking");
    try {
      const before = state?.json;
      const next = await request(`/api/sync/${sourceMode}`, {source, revision: ownRevision});
      if (next.revision < latestApplied || ownRevision !== revision) return false;
      if (history && before && before !== next.json) {
        undoStack.push(before);
        if (undoStack.length > 80) undoStack.shift();
        redoStack.length = 0;
      }
      drafts[sourceMode] = null;
      invalid[sourceMode] = false;
      stale[sourceMode] = false;
      const otherMode = sourceMode === "python" ? "json" : "python";
      if (invalid[otherMode] && drafts[otherMode] !== null) stale[otherMode] = true;
      renderState(next, {keepEditor: keepEditor && mode === sourceMode});
      if (mode === sourceMode) {
        const start = editor.selectionStart;
        editor.value = next[sourceMode];
        editor.selectionStart = editor.selectionEnd = Math.min(start, editor.value.length);
        lineNumbers();
      }
      if (stale[mode]) {
        setStatus("stale", "Stale");
        setDiagnostic("This draft is based on an older score. Press Ctrl+Enter to apply it, or use Format to discard it.", true);
      } else {
        setStatus("synced", "Synced");
        setDiagnostic(next.relaid ? "Notation was relaid out from the Python expression." : "All views match the committed Score Model.");
      }
      return true;
    } catch (error) {
      if (error.revision && error.revision < revision) return false;
      invalid[sourceMode] = true;
      setStatus("invalid", "Invalid");
      setDiagnostic(error.message, true);
      return false;
    } finally {
      syncing = false;
    }
  }

  function scheduleSync() {
    clearTimeout(timer);
    drafts[mode] = editor.value;
    if (stale[mode]) {
      setStatus("stale", "Stale");
      setDiagnostic("This draft is based on an older score. Press Ctrl+Enter to apply it, or use Format to discard it.", true);
      return;
    }
    invalid[mode] = false;
    setStatus("editing", "Editing");
    setDiagnostic("Waiting for you to pause typing…");
    timer = setTimeout(() => syncDraft(editor.value, mode), 400);
  }

  function switchMode(nextMode) {
    if (nextMode === mode) return;
    clearTimeout(timer);
    mode = nextMode;
    $$(".source-tabs button").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
    editor.value = drafts[mode] ?? state[mode];
    lineNumbers();
    if (stale[mode]) {
      setStatus("stale", "Stale");
      setDiagnostic("This draft is based on an older score. Press Ctrl+Enter to apply it, or use Format to discard it.", true);
    } else if (invalid[mode]) {
      setStatus("invalid", "Invalid"); setDiagnostic("This draft is invalid and has not changed the score.", true);
    } else {
      setStatus("synced", "Synced");
      setDiagnostic(mode === "python" ? "Python is a semantic projection. Musical layout stays in the score."
        : "JSON exposes the complete, lossless Score Model.");
    }
  }

  async function applyInspector() {
    const candidate = structuredClone(state.score);
    const events = [];
    candidate.score.parts.forEach(part => part.staves.forEach(staff => staff.measures.forEach(measure =>
      measure.voices.forEach(voice => voice.events.forEach(event => events.push(event))))));
    const event = events.find(item => item.id === selectedEvent);
    if (!event || event.type === "rest") return;
    const pitch = event.pitch || event.pitches[0];
    pitch.step = $("#pitchStep").value;
    pitch.octave = Number($("#pitchOctave").value);
    const accidental = $("#accidental").value;
    pitch.alter = accidental === "sharp" ? 1 : accidental === "flat" ? -1 : 0;
    if (accidental) event.accidental = accidental; else delete event.accidental;
    const stem = $("#stem").value;
    if (stem) event.stem = stem; else delete event.stem;
    if (!$("#eventDuration").disabled) {
      const [n, d] = $("#eventDuration").value.split("/").map(Number);
      event.duration = {n, d};
    }
    const jsonSource = JSON.stringify(candidate, null, 2) + "\n";
    setStatus("checking", "Checking");
    if (await syncDraft(jsonSource, "json", {keepEditor: mode !== "json"})) toast("Notation updated", `${selectedEvent} is now ${pitchText(event)}.`);
    else renderState(state, {keepEditor: true});
  }

  async function applyNotationTool(eventId) {
    const candidate = structuredClone(state.score);
    let target;
    let targetLocation;
    candidate.score.parts.forEach(part => part.staves.forEach(staff => staff.measures.forEach(measure =>
      measure.voices.forEach((voice, voiceIndex) => voice.events.forEach(event => {
        if (event.id === eventId) { target = event; targetLocation = {staff: voice.staff, voice: voiceIndex + 1, measure: measure.number}; }
      }))
    )));
    if (!target) return;
    if (currentTool === "note" && target.type === "rest") {
      target.type = "note";
      target.pitch = {step: "C", alter: 0, octave: 4};
      const ok = await syncDraft(JSON.stringify(candidate, null, 2) + "\n", "json", {keepEditor: mode !== "json"});
      if (ok) { toast("Note inserted", `${eventId} now carries pitch C4.`); selectTool("select"); selectEvent(eventId); }
      else renderState(state, {keepEditor: true});
      return;
    }
    if (["tie", "slur", "bracket"].includes(currentTool)) {
      if (!toolAnchor) {
        toolAnchor = eventId;
        selectEvent(eventId);
        toast(`${currentTool[0].toUpperCase()}${currentTool.slice(1)} start selected`, "Now choose the ending event.");
        return;
      }
      const locations = new Map();
      candidate.score.parts.forEach(part => part.staves.forEach(staff => staff.measures.forEach(measure =>
        measure.voices.forEach((voice, voiceIndex) => voice.events.forEach(event =>
          locations.set(event.id, {staff: voice.staff, voice: voiceIndex + 1, measure: measure.number})))
      )));
      const startLocation = locations.get(toolAnchor);
      if (!startLocation || startLocation.measure !== targetLocation.measure) {
        toast("Cannot create grouping", "Both anchors must be in the same measure in Codetta v0.1.");
        toolAnchor = null;
        return;
      }
      const existingIndex = candidate.score.spanners.findIndex(spanner => spanner.type === currentTool &&
        ((spanner.start_anchor === toolAnchor && spanner.end_anchor === eventId) ||
         (spanner.start_anchor === eventId && spanner.end_anchor === toolAnchor)));
      let removed = false;
      if (existingIndex >= 0) {
        candidate.score.spanners.splice(existingIndex, 1);
        removed = true;
      } else {
        const number = candidate.score.spanners.reduce((largest, spanner) => {
          const match = /(?:spanner|composer)-(\d+)$/.exec(spanner.id);
          return Math.max(largest, match ? Number(match[1]) : 0);
        }, 0) + 1;
        candidate.score.spanners.push({
          id: `composer-${number}`, type: currentTool, line_style: "solid",
          start_anchor: toolAnchor, end_anchor: eventId,
          staff_range: [Math.min(startLocation.staff, targetLocation.staff), Math.max(startLocation.staff, targetLocation.staff)],
          voice_range: [Math.min(startLocation.voice, targetLocation.voice), Math.max(startLocation.voice, targetLocation.voice)],
          nesting_level: currentTool === "tie" ? 0 : Math.max(0, ...candidate.score.spanners.filter(item => item.type !== "tie").map(item => item.nesting_level + 1)),
        });
      }
      const toolName = currentTool;
      const ok = await syncDraft(JSON.stringify(candidate, null, 2) + "\n", "json", {keepEditor: mode !== "json"});
      toolAnchor = null;
      if (ok) {
        toast(`${toolName[0].toUpperCase()}${toolName.slice(1)} ${removed ? "removed" : "created"}`, `${eventId} is the ending anchor.`);
        selectTool("select"); selectEvent(eventId);
      } else renderState(state, {keepEditor: true});
      return;
    }
    if (currentTool === "rest" && target.type !== "rest") {
      target.type = "rest";
      delete target.pitch; delete target.pitches; delete target.accidental; delete target.stem;
      const ok = await syncDraft(JSON.stringify(candidate, null, 2) + "\n", "json", {keepEditor: mode !== "json"});
      if (ok) { toast("Rest inserted", `${eventId} is now a rest.`); selectTool("select"); selectEvent(eventId); }
      else renderState(state, {keepEditor: true});
      return;
    }
    toast(`${currentTool[0].toUpperCase()}${currentTool.slice(1)} tool`, currentTool === "note" || currentTool === "rest"
      ? "Choose an event of the opposite type to replace it without changing the timeline."
      : "For precise structural grouping, select the JSON view and edit score.spanners; every change is validated atomically.");
  }

  function selectTool(tool) {
    currentTool = tool;
    toolAnchor = null;
    $$(".notation-toolbar .tool").forEach(item => item.classList.toggle("active", item.dataset.tool === tool));
  }

  async function undo() {
    if (!undoStack.length || syncing) return;
    const source = undoStack.pop();
    redoStack.push(state.json);
    await syncDraft(source, "json", {history: false, keepEditor: false});
    toast("Undo", "Restored the previous committed score.");
  }

  async function redo() {
    if (!redoStack.length || syncing) return;
    const source = redoStack.pop();
    undoStack.push(state.json);
    await syncDraft(source, "json", {history: false, keepEditor: false});
    toast("Redo", "Restored the next committed score.");
  }

  function saveFile() {
    const blob = new Blob([state.json], {type: "application/json"});
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = $("#scoreFile span").textContent;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    savedJson = state.json;
    document.body.classList.remove("dirty");
    toast("Score saved", link.download);
  }

  async function openFile(file) {
    if (!file) return;
    const source = await file.text();
    if (await syncDraft(source, "json")) {
      savedJson = state.json;
      document.body.classList.remove("dirty");
      toast("Score opened", file.name);
    }
  }

  async function play() {
    const button = $("#playButton");
    button.innerHTML = `${icon("info")}<span>Rendering…</span>`;
    try {
      const response = await fetch("/api/audio", {method: "POST"});
      if (!response.ok) throw new Error("Could not render audio");
      const audio = new Audio(URL.createObjectURL(await response.blob()));
      button.innerHTML = `${icon("play")}<span>Playing</span>`;
      audio.addEventListener("ended", () => button.innerHTML = `${icon("play")}<span>Run score</span>`, {once: true});
      await audio.play();
    } catch (error) {
      button.innerHTML = `${icon("play")}<span>Run score</span>`;
      toast("Playback failed", error.message);
    }
  }

  function toggleSource(force) {
    sourceVisible = force ?? !sourceVisible;
    grid.classList.toggle("source-hidden", !sourceVisible);
    $("#toggleSource").style.color = sourceVisible ? "var(--accent-2)" : "";
  }

  function toggleDebug() {
    debug = !debug;
    document.body.classList.toggle("debug", debug);
    $("#debugButton").style.color = debug ? "var(--accent-2)" : "";
    if (state) $("#scoreSvg").innerHTML = debug ? state.debug_svg : state.svg;
    toast(debug ? "Debug overlay enabled" : "Debug overlay hidden", debug ? "Semantic groups are annotated on a separate rendering layer." : "The score is back in normal notation mode.");
  }

  function showCommands() {
    const dialog = $("#commandDialog");
    dialog.showModal();
    $("#commandInput").value = "";
    $$(".command-list button").forEach(button => button.hidden = false);
    $("#commandInput").focus();
  }

  function runCommand(command) {
    $("#commandDialog").close();
    ({save: saveFile, open: () => $("#fileInput").click(), run: play,
      "toggle-source": toggleSource, debug: toggleDebug})[command]?.();
  }

  editor.addEventListener("input", scheduleSync);
  editor.addEventListener("scroll", () => $("#lineNumbers").scrollTop = editor.scrollTop);
  editor.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && stale[mode]) {
      event.preventDefault();
      stale[mode] = false;
      syncDraft(editor.value, mode);
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      const start = editor.selectionStart;
      editor.setRangeText("  ", start, editor.selectionEnd, "end");
      scheduleSync();
    }
  });
  $$(".source-tabs button").forEach(button => button.addEventListener("click", () => switchMode(button.dataset.mode)));
  $("#formatButton").addEventListener("click", () => {
    editor.value = state[mode]; lineNumbers(); drafts[mode] = null; invalid[mode] = false; stale[mode] = false;
    setStatus("synced", "Synced"); setDiagnostic("Draft reset to the last committed, normalized projection.");
  });
  $("#closeSource").addEventListener("click", () => toggleSource(false));
  $("#toggleSource").addEventListener("click", () => toggleSource());
  $("#debugButton").addEventListener("click", toggleDebug);
  $("#playButton").addEventListener("click", play);
  $("#resultStatus").addEventListener("click", () => toast("Exact result", state.result));
  $("#zoomIn").addEventListener("click", () => { zoom = Math.min(1.5, zoom + .1); updateZoom(); });
  $("#zoomOut").addEventListener("click", () => { zoom = Math.max(.6, zoom - .1); updateZoom(); });
  function updateZoom() { $("#scoreSvg").style.zoom = zoom; $("#zoomLabel").textContent = `${Math.round(zoom * 100)}%`; }
  $$("#pitchStep,#pitchOctave,#accidental,#stem,#eventDuration").forEach(control => control.addEventListener("change", applyInspector));
  $("#closeInspector").addEventListener("click", () => { selectedEvent = null; renderEventList(); $("#inspectorFields").hidden = true; $("#inspectorEmpty").hidden = false; $("#inspectorEmpty").textContent = "Select a notation event to edit it."; });
  $$(".outline button").forEach(button => button.addEventListener("click", () => {
    if (button.dataset.focus === "source") { toggleSource(true); editor.focus(); }
    else $("#scoreScroll").focus();
  }));
  $$(".notation-toolbar .tool").forEach(button => button.addEventListener("click", () => {
    selectTool(button.dataset.tool);
    if (button.dataset.tool !== "select") toast(`${button.textContent.trim()} tool selected`, button.dataset.tool === "note" || button.dataset.tool === "rest"
      ? "Choose an event below the score to replace it on the existing timeline."
      : "Choose the JSON view for validated spanner editing.");
  }));
  $$(".duration-group button").forEach(button => button.addEventListener("click", () => {
    $$(".duration-group button").forEach(item => item.classList.remove("active")); button.classList.add("active");
    const selected = allEvents().find(item => item.event.id === selectedEvent)?.event;
    if (selected && selected.type !== "rest" && !$("#eventDuration").disabled) {
      $("#eventDuration").value = button.dataset.duration;
      applyInspector();
    } else toast("Input duration", selected ? "Tied values are respelled safely from the Python pane." : "Select an untied note first.");
  }));
  $("#fileInput").addEventListener("change", event => openFile(event.target.files[0]));
  $("#commandTitle").parentElement.addEventListener("click", showCommands);
  $("#commandInput").addEventListener("input", event => {
    const query = event.target.value.toLowerCase();
    $$(".command-list button").forEach(button => button.hidden = !button.textContent.toLowerCase().includes(query));
  });
  $$(".command-list button").forEach(button => button.addEventListener("click", () => runCommand(button.dataset.command)));
  $("#commandDialog").addEventListener("click", event => { if (event.target === $("#commandDialog")) $("#commandDialog").close(); });

  const resizer = $("#resizer");
  resizer.addEventListener("pointerdown", event => {
    resizer.setPointerCapture(event.pointerId); resizer.classList.add("dragging");
  });
  resizer.addEventListener("pointermove", event => {
    if (!resizer.hasPointerCapture(event.pointerId)) return;
    const bounds = grid.getBoundingClientRect();
    const right = Math.max(330, Math.min(bounds.width - 390, bounds.right - event.clientX));
    grid.style.gridTemplateColumns = `minmax(390px, 1fr) 4px ${right}px`;
  });
  resizer.addEventListener("pointerup", event => { resizer.releasePointerCapture(event.pointerId); resizer.classList.remove("dragging"); });

  document.addEventListener("keydown", event => {
    const ctrl = event.ctrlKey || event.metaKey;
    if (ctrl && event.key.toLowerCase() === "s") { event.preventDefault(); saveFile(); }
    if (ctrl && event.key.toLowerCase() === "o") { event.preventDefault(); $("#fileInput").click(); }
    if (ctrl && event.key.toLowerCase() === "z" && !event.shiftKey && document.activeElement !== editor) { event.preventDefault(); undo(); }
    if (ctrl && (event.key.toLowerCase() === "y" || (event.shiftKey && event.key.toLowerCase() === "z")) && document.activeElement !== editor) { event.preventDefault(); redo(); }
    if ((ctrl && event.shiftKey && event.key.toLowerCase() === "p") || (ctrl && event.key.toLowerCase() === "k")) { event.preventDefault(); showCommands(); }
    if (ctrl && event.key.toLowerCase() === "j") { event.preventDefault(); toggleSource(); }
    if (event.key === "F5") { event.preventDefault(); play(); }
    if (event.key === "Escape" && $("#commandDialog").open) $("#commandDialog").close();
  });

  fetch("/api/state").then(response => response.json()).then(initial => {
    savedJson = initial.json;
    renderState(initial);
    setStatus("synced", "Synced");
    setDiagnostic("Python is a semantic projection. Musical layout stays in the score.");
  }).catch(error => {
    $("#renderLoading").innerHTML = `<span></span><span>Could not start Composer: ${error.message}</span>`;
    setStatus("invalid", "Offline");
  });
})();
