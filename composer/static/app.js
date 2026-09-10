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
  let selectedVoice = null;
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
        voice.events.forEach(event => items.push({event, staff: staffIndex + 1, voice: voiceIndex + 1,
          voiceId: voice.id, voiceName: voice.name, measure: measure.number}))
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

  function scoreDocument() { return state?.score; }
  function isV02(document = scoreDocument()) { return document?.language_version === "0.2"; }

  function uniqueVoices(document = scoreDocument()) {
    const values = new Map();
    document.score.parts.forEach(part => part.staves.forEach(staff => staff.measures.forEach(measure =>
      measure.voices.forEach((voice, lane) => values.set(voice.id, {
        id: voice.id, name: voice.name || "", staff: voice.staff, lane: lane + 1,
      }))
    )));
    return [...values.values()].sort((left, right) => left.staff - right.staff || left.id.localeCompare(right.id));
  }

  function structureNode(label, detail, kind, active = false, action = null) {
    const button = document.createElement("button");
    button.className = `structure-node ${active ? "active" : ""}`;
    button.innerHTML = `${icon(kind)}<span></span><small></small>`;
    button.querySelector("span").textContent = label;
    button.querySelector("small").textContent = detail;
    if (action) button.addEventListener("click", action);
    return button;
  }

  function renderStructureTree() {
    const tree = $("#structureTree");
    tree.replaceChildren();
    const enabled = isV02();
    $$("#structureActions button").forEach(button => button.disabled = !enabled);
    if (!enabled) {
      const hint = document.createElement("p");
      hint.textContent = "Type a v0.2 program in the Python pane to create named Voices and musical control structures.";
      tree.append(hint);
      return;
    }
    const body = bodyScore();
    const voices = uniqueVoices();
    const label = document.createElement("div"); label.className = "structure-label"; label.textContent = "VOICES"; tree.append(label);
    voices.filter(voice => voice.name).forEach(voice => tree.append(structureNode(
      voice.name, `S${voice.staff} · V${voice.lane}`, "music", voice.id === selectedVoice, () => {
        selectedVoice = voice.id;
        const first = allEvents().find(item => item.voiceId === voice.id);
        if (first) selectEvent(first.event.id);
        renderStructureTree();
      }
    )));
    if (body.sections.length) {
      const heading = document.createElement("div"); heading.className = "structure-label"; heading.textContent = "SECTIONS"; tree.append(heading);
      body.sections.forEach(item => tree.append(structureNode(item.name, item.rehearsal_mark, "score")));
    }
    const structures = [
      ["Repeat", body.repeats.length], ["Volta", body.voltas.length],
      ["Array phrase", body.phrases.length], ["Struct", body.voice_groups.length],
      ["Call", body.section_references.length],
    ];
    structures.filter(([, count]) => count).forEach(([name, count]) =>
      tree.append(structureNode(name, String(count), "branch")));
  }

  function nextId(document, prefix) {
    const ids = [];
    const visit = value => {
      if (!value || typeof value !== "object") return;
      if (typeof value.id === "string") ids.push(value.id);
      Object.values(value).forEach(item => Array.isArray(item) ? item.forEach(visit) : visit(item));
    };
    visit(document.score);
    let number = 1;
    while (ids.includes(`${prefix}-${number}`)) number += 1;
    return `${prefix}-${number}`;
  }

  function parseNames(document, text, label, {allowEmpty = true} = {}) {
    const names = text.split(",").map(item => item.trim()).filter(Boolean);
    if (!allowEmpty && !names.length) throw new Error(`${label} needs at least one Voice name.`);
    const voices = uniqueVoices(document);
    return names.map(token => {
      const qualified = token.match(/^(.*)@S(\d+)$/i);
      const matches = voices.filter(voice => voice.id === token ||
        (qualified ? voice.name === qualified[1] && voice.staff === Number(qualified[2]) : voice.name === token));
      if (matches.length !== 1) throw new Error(`${label}: Voice ${token} was not found or is ambiguous. Use name@Snumber or its ID.`);
      return matches[0].id;
    });
  }

  function measureId(document, number) {
    const measures = document.score.parts[0].staves[0].measures;
    if (!Number.isInteger(number) || number < 1 || number > measures.length) throw new Error(`Measure ${number} does not exist.`);
    return measures[number - 1].id;
  }

  async function commitStructure(document, title, detail) {
    const ok = await syncDraft(JSON.stringify(document, null, 2) + "\n", "json", {keepEditor: mode !== "json"});
    if (ok) toast(title, detail);
  }

  async function addVoice() {
    const name = prompt("Voice name");
    if (name === null) return;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return toast("Invalid Voice name", "Use a programming identifier such as total or values.");
    const candidate = structuredClone(scoreDocument());
    if (uniqueVoices(candidate).some(voice => voice.name === name)) return toast("Voice already exists", name);
    const part = candidate.score.parts[0];
    const voiceId = nextId(candidate, "composer-voice");
    const available = part.staves.find(staff => staff.measures[0].voices.length < 4);
    if (available) {
      const staffNumber = part.staves.indexOf(available) + 1;
      available.measures.forEach(measure => measure.voices.push({
        id: voiceId, staff: staffNumber, name, events: [],
      }));
    } else {
      const staffNumber = part.staves.length + 1;
      const template = part.staves[0].measures;
      part.staves.push({
        id: nextId(candidate, "composer-staff"),
        measures: template.map(measure => ({
          ...structuredClone(measure), id: `composer-measure-${staffNumber}-${measure.number}`,
          voices: [{id: voiceId, staff: staffNumber, name, events: []}],
        })),
      });
    }
    selectedVoice = voiceId;
    await commitStructure(candidate, "Voice created", name);
  }

  async function renameVoice() {
    if (!selectedVoice) return toast("Select a Voice", "Choose a named Voice in Program Structure first.");
    const candidate = structuredClone(scoreDocument());
    const current = uniqueVoices(candidate).find(voice => voice.id === selectedVoice);
    const name = prompt("New Voice name", current?.name || "");
    if (name === null || name === current?.name) return;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return toast("Invalid Voice name", name);
    candidate.score.parts.forEach(part => part.staves.forEach(staff => staff.measures.forEach(measure =>
      measure.voices.forEach(voice => { if (voice.id === selectedVoice) voice.name = name; })
    )));
    await commitStructure(candidate, "Voice renamed", `${current?.name} → ${name}`);
  }

  async function addValue() {
    if (!selectedVoice) return toast("Select a Voice", "Choose a named Voice in Program Structure first.");
    const candidate = structuredClone(scoreDocument());
    const selectedMeasure = allEvents().find(item => item.event.id === selectedEvent)?.measure || 1;
    const number = Number(prompt("Measure number", String(selectedMeasure)));
    const value = Number(prompt("Nonnegative Int value (0 creates a rest)", "1"));
    try {
      if (!Number.isInteger(value) || value < 0 || value > 4096) {
        throw new Error("Int value must be a whole number from 0 through 4096.");
      }
      const staff = candidate.score.parts[0].staves.find(item =>
        item.measures.some(measure => measure.voices.some(voice => voice.id === selectedVoice)));
      const measure = staff?.measures[number - 1];
      const voice = measure?.voices.find(item => item.id === selectedVoice);
      if (!voice) throw new Error(`Voice is not available in measure ${number}.`);
      if (voice.events.length) throw new Error("That Voice already has a value in this measure.");
      const capacity = measure.time_signature.beats * 4 / measure.time_signature.beat_type;
      if (Math.max(1, value) > capacity) throw new Error(`Value does not fit in this ${capacity}-beat measure.`);
      const event = {type: value === 0 ? "rest" : "note", id: nextId(candidate, "composer-event"),
        start: {n: 0, d: 1}, duration: {n: Math.max(1, value), d: 4}};
      if (value !== 0) event.pitch = {step: "C", alter: 0, octave: 4};
      voice.events.push(event);
      selectedEvent = event.id;
      await commitStructure(candidate, "Value placed", `${value} on ${voice.name} · measure ${number}`);
    } catch (error) { toast("Cannot place value", error.message); }
  }

  async function addSection() {
    const candidate = structuredClone(scoreDocument());
    const name = prompt("Function section name"); if (name === null) return;
    const mark = prompt("Rehearsal mark", String.fromCharCode(65 + candidate.score.sections.length)); if (mark === null) return;
    const first = Number(prompt("First measure number", "1"));
    const last = Number(prompt("Last measure number", String(candidate.score.parts[0].staves[0].measures.length)));
    const parameters = prompt("Parameter Voice names, comma separated", "") ?? "";
    const returns = prompt("Return Voice names, comma separated", "result") ?? "";
    try {
      candidate.score.sections.push({id: nextId(candidate, "composer-section"), name, rehearsal_mark: mark,
        start_measure: measureId(candidate, first), end_measure: measureId(candidate, last),
        parameter_voice_ids: parseNames(candidate, parameters, "Parameters"),
        return_voice_ids: parseNames(candidate, returns, "Returns")});
      await commitStructure(candidate, "Function section created", name);
    } catch (error) { toast("Cannot create section", error.message); }
  }

  async function addRepeat() {
    const candidate = structuredClone(scoreDocument());
    const first = Number(prompt("Repeat first measure", "1"));
    const last = Number(prompt("Repeat last measure", String(first)));
    const mode = (prompt("Repeat mode: for or while", "for") || "").trim().toLowerCase();
    try {
      const repeat = {id: nextId(candidate, "composer-repeat"),
        start_measure: measureId(candidate, first), end_measure: measureId(candidate, last), test_at_end: false};
      if (mode === "while") {
        const conditionName = prompt("Bool condition Voice (name@Snumber or ID)", "condition");
        if (conditionName === null) return;
        repeat.condition_voice_id = parseNames(candidate, conditionName, "Condition", {allowEmpty: false})[0];
      } else if (mode === "for") {
        const iteratorName = prompt("Iterator Voice (name@Snumber or ID)", "i");
        if (iteratorName === null) return;
        repeat.iterator_voice_id = parseNames(candidate, iteratorName, "Iterator", {allowEmpty: false})[0];
        const source = (prompt("Count: integer, Voice, or length(Voice)", "4") || "").trim();
        if (/^\d+$/.test(source)) repeat.times = Number(source);
        else {
          const collection = source.match(/^length\((.+)\)$/);
          const key = collection ? "collection_voice_id" : "count_voice_id";
          repeat[key] = parseNames(candidate, collection ? collection[1].trim() : source,
            collection ? "Collection" : "Count", {allowEmpty: false})[0];
        }
      } else throw new Error("Repeat mode must be for or while.");
      candidate.score.repeats.push(repeat);
      await commitStructure(candidate, `${mode === "while" ? "Conditional" : "Counted"} repeat created`,
        `Measures ${first}–${last}`);
    } catch (error) { toast("Cannot create repeat", error.message); }
  }

  async function addVolta() {
    const candidate = structuredClone(scoreDocument());
    const conditionName = prompt("Bool condition Voice name", "condition"); if (conditionName === null) return;
    const trueRange = (prompt("True ending measures (start-end)", "1-1") || "").split("-").map(Number);
    const falseText = prompt("False ending measures (start-end), blank for no else", "");
    try {
      const condition = parseNames(candidate, conditionName, "Condition", {allowEmpty: false})[0];
      const endings = [{numbers: [1], start_measure: measureId(candidate, trueRange[0]),
        end_measure: measureId(candidate, trueRange[1])}];
      if (falseText) {
        const range = falseText.split("-").map(Number);
        endings.push({numbers: [2], start_measure: measureId(candidate, range[0]), end_measure: measureId(candidate, range[1])});
      }
      candidate.score.voltas.push({id: nextId(candidate, "composer-volta"), condition_voice_id: condition, endings});
      await commitStructure(candidate, "Volta branch created", falseText ? "if / else" : "if");
    } catch (error) { toast("Cannot create volta", error.message); }
  }

  async function addArray() {
    const candidate = structuredClone(scoreDocument());
    const start = prompt("First element event ID", selectedEvent || ""); if (!start) return;
    const end = prompt("Last element event ID", start); if (!end) return;
    const output = prompt("Array output event ID", selectedEvent || ""); if (!output) return;
    const location = allEvents().find(item => item.event.id === start);
    if (!location) return toast("Cannot create Array", "The first event was not found.");
    candidate.score.phrases.push({id: nextId(candidate, "composer-phrase"), start_anchor: start,
      end_anchor: end, voice_ids: [location.voiceId], output_anchor: output});
    await commitStructure(candidate, "Array phrase created", `${start} → ${end}`);
  }

  async function addStruct() {
    const candidate = structuredClone(scoreDocument());
    const name = prompt("Struct group name", "record"); if (!name) return;
    const members = prompt("Field Voice names, comma separated", ""); if (members === null) return;
    const output = prompt("Struct output event ID (blank for a persistent Voice group)", selectedEvent || "");
    try {
      const item = {id: nextId(candidate, "composer-voice-group"), name,
        voice_ids: parseNames(candidate, members, "Struct fields", {allowEmpty: false})};
      if (output) item.output_anchor = output;
      candidate.score.voice_groups.push(item);
      await commitStructure(candidate, "Struct group created", name);
    } catch (error) { toast("Cannot create Struct", error.message); }
  }

  async function addCall() {
    const candidate = structuredClone(scoreDocument());
    const sectionName = prompt("Function section name"); if (!sectionName) return;
    const section = candidate.score.sections.find(item => item.name === sectionName);
    if (!section) return toast("Cannot create Call", `Section ${sectionName} was not found.`);
    const anchor = prompt("Call result event ID", selectedEvent || ""); if (!anchor) return;
    const argumentsText = prompt("Argument Voice names, comma separated", "") ?? "";
    const resultsText = prompt("Result Voice names, comma separated", "result") ?? "";
    try {
      candidate.score.section_references.push({id: nextId(candidate, "composer-call"),
        section_id: section.id, anchor,
        argument_voice_ids: parseNames(candidate, argumentsText, "Arguments"),
        result_voice_ids: parseNames(candidate, resultsText, "Results", {allowEmpty: false})});
      await commitStructure(candidate, "Function call created", sectionName);
    } catch (error) { toast("Cannot create Call", error.message); }
  }

  function selectEvent(id) {
    selectedEvent = id;
    renderEventList();
    renderStructureTree();
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
    renderStructureTree();
    $("#languageVersion").textContent = `Codetta v${next.score.language_version}`;
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
  const structureCommands = {voice: addVoice, value: addValue, rename: renameVoice, section: addSection,
    repeat: addRepeat, volta: addVolta, array: addArray, struct: addStruct, call: addCall};
  $$("#structureActions button").forEach(button => button.addEventListener("click", () =>
    structureCommands[button.dataset.structure]?.()));
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
