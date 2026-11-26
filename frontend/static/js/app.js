// State
let projects = [];
let activeProjectId = null;
let activeRequestId = null;
let currentRequestData = null;
let currentRawResponse = "";

// DOM Elements
const projectsListEl = document.getElementById("projectsList");
const noSelectionStateEl = document.getElementById("noSelectionState");
const activeRequestContainerEl = document.getElementById("activeRequestContainer");

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadProjects();

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      runRequest();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveCurrentRequest();
    }
  });
});

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2200);
}

// View Switching (Workspace vs Docs)
function switchMainView(viewName) {
  document.querySelectorAll(".nav-tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".view-pane").forEach(p => p.classList.remove("active"));

  if (viewName === "client") {
    document.getElementById("navBtnClient").classList.add("active");
    document.getElementById("viewClient").classList.add("active");
  } else if (viewName === "docs") {
    document.getElementById("navBtnDocs").classList.add("active");
    document.getElementById("viewDocs").classList.add("active");
  }
}

// Projects Management
async function loadProjects() {
  try {
    projects = await ApiService.getProjects();
    renderProjects();
    if (activeProjectId) {
      const exists = projects.some(p => p.id === activeProjectId);
      if (!exists && projects.length > 0) {
        selectProject(projects[0].id);
      }
    }
  } catch (err) {
    console.error("Failed to load projects", err);
  }
}

function renderProjects() {
  projectsListEl.innerHTML = "";
  if (projects.length === 0) {
    projectsListEl.innerHTML = `
      <div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 20px 0;">
        No projects yet.<br><br>
        <button class="btn btn-sm" onclick="openNewProjectModal()">+ New Project</button><br><br>
        or <a href="#" style="color: #60a5fa;" onclick="switchMainView('docs')">Import Sample</a>
      </div>`;
    return;
  }

  projects.forEach(p => {
    const isActive = p.id === activeProjectId;
    const card = document.createElement("div");
    card.className = `project-card ${isActive ? 'active' : ''}`;
    card.id = `project-card-${p.id}`;

    card.innerHTML = `
      <div class="project-card-header" onclick="selectProject(${p.id})">
        <span class="project-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          ${escapeHtml(p.name)}
        </span>
        <div class="project-actions" onclick="event.stopPropagation()">
          <button class="btn-icon" title="New Request" onclick="createNewRequest(${p.id})">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
          </button>
          <button class="btn-icon" title="Delete Project" onclick="deleteProject(${p.id}, '${escapeHtml(p.name)}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
        </div>
      </div>
      <div class="project-details">
        <div class="base-url-bar">
          <span style="font-size: 0.75rem; color: var(--text-muted);">Base URL:</span>
          <input type="text" value="${escapeHtml(p.base_url || '')}" placeholder="https://api..." onchange="updateProjectBaseUrl(${p.id}, this.value)">
        </div>
        <ul class="requests-list" id="req-list-${p.id}">
          <li style="color: var(--text-muted); font-size: 0.78rem;">Loading requests...</li>
        </ul>
      </div>
    `;

    projectsListEl.appendChild(card);
    if (isActive) {
      loadProjectRequests(p.id);
    }
  });
}

async function selectProject(projectId) {
  if (activeProjectId === projectId) return;
  activeProjectId = projectId;
  renderProjects();
}

async function loadProjectRequests(projectId) {
  try {
    const reqs = await ApiService.getProjectRequests(projectId);
    const listEl = document.getElementById(`req-list-${projectId}`);
    if (!listEl) return;

    listEl.innerHTML = "";
    if (reqs.length === 0) {
      listEl.innerHTML = `<li style="color: var(--text-muted); font-size: 0.78rem; padding: 4px;">No requests. Click <b>+</b> above.</li>`;
      return;
    }

    reqs.forEach(r => {
      const li = document.createElement("li");
      li.className = `request-item ${r.id === activeRequestId ? 'active' : ''}`;
      li.onclick = () => selectRequest(r.id);
      li.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
          <span class="req-badge badge-${r.method.toLowerCase()}">${r.method}</span>
          <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(r.name)}</span>
        </div>
      `;
      listEl.appendChild(li);
    });

    if (activeRequestId && !reqs.some(r => r.id === activeRequestId)) {
      activeRequestId = null;
      showNoSelection();
    } else if (!activeRequestId && reqs.length > 0) {
      selectRequest(reqs[0].id);
    }
  } catch (err) {
    console.error("Failed to load requests", err);
  }
}

async function updateProjectBaseUrl(projectId, newUrl) {
  try {
    await ApiService.updateProject(projectId, { base_url: newUrl });
    const proj = projects.find(p => p.id === projectId);
    if (proj) proj.base_url = newUrl;
    showToast("Base URL saved");
  } catch (err) {
    console.error("Failed to update base url", err);
  }
}

async function deleteProject(projectId, name) {
  if (!confirm(`Delete project "${name}" and all its requests?`)) return;
  try {
    await ApiService.deleteProject(projectId);
    if (activeProjectId === projectId) {
      activeProjectId = null;
      activeRequestId = null;
      showNoSelection();
    }
    loadProjects();
    showToast("Project deleted");
  } catch (err) {
    console.error("Failed to delete project", err);
  }
}

// Request Operations
async function createNewRequest(projectId) {
  try {
    const newReq = await ApiService.createRequest(projectId, {
      name: "New Request",
      method: "GET",
      url: ""
    });
    activeProjectId = projectId;
    activeRequestId = newReq.id;
    await loadProjects();
    selectRequest(newReq.id);
    switchMainView('client');
    showToast("Request created");
  } catch (err) {
    console.error("Failed to create request", err);
  }
}

async function selectRequest(reqId) {
  activeRequestId = reqId;
  try {
    currentRequestData = await ApiService.getRequest(reqId);
    populateRequestForm(currentRequestData);
    noSelectionStateEl.style.display = "none";
    activeRequestContainerEl.style.display = "flex";

    document.querySelectorAll(".request-item").forEach(el => el.classList.remove("active"));
    if (activeProjectId) {
      loadProjectRequests(activeProjectId);
    }
    switchMainView('client');
  } catch (err) {
    console.error("Failed to get request details", err);
  }
}

function showNoSelection() {
  noSelectionStateEl.style.display = "flex";
  activeRequestContainerEl.style.display = "none";
}

function populateRequestForm(data) {
  document.getElementById("requestName").value = data.name || "Untitled Request";
  document.getElementById("requestMethod").value = data.method || "GET";
  document.getElementById("requestUrl").value = data.url || "";

  populateKvTable("headersTableBody", data.headers || []);
  populateKvTable("paramsTableBody", data.params || []);
  const bodyType = data.body_type || "none";
  const radio = document.querySelector(`input[name="bodyType"][value="${bodyType}"]`);
  if (radio) radio.checked = true;
  toggleBodyType(bodyType);

  document.getElementById("bodyRawJson").value = data.body_raw || "";
  populateKvTable("formDataTableBody", data.body_form || []);

  document.getElementById("responseMetrics").innerHTML = `<span style="color: var(--text-muted);">Ready to send</span>`;
  document.getElementById("responseBodyDisplay").innerHTML = `<span style="color: var(--text-muted);">Press Run or Ctrl+Enter to execute</span>`;
  document.getElementById("respHeadersTableBody").innerHTML = "";
}

function getFormDataFromUi() {
  const headers = readKvTable("headersTableBody");
  const params = readKvTable("paramsTableBody");
  const bodyForm = readKvTable("formDataTableBody");
  const bodyType = document.querySelector('input[name="bodyType"]:checked').value;
  const bodyRaw = document.getElementById("bodyRawJson").value;

  return {
    name: document.getElementById("requestName").value.trim(),
    method: document.getElementById("requestMethod").value,
    url: document.getElementById("requestUrl").value.trim(),
    headers: headers,
    params: params,
    body_type: bodyType,
    body_raw: bodyRaw,
    body_form: bodyForm
  };
}

async function saveCurrentRequest() {
  if (!activeRequestId) return;
  const payload = getFormDataFromUi();
  try {
    currentRequestData = await ApiService.updateRequest(activeRequestId, payload);
    showToast("Request saved!");
    if (activeProjectId) {
      loadProjectRequests(activeProjectId);
    }
  } catch (err) {
    console.error("Failed to save request", err);
  }
}

function autoSaveCurrentRequest() {
  saveCurrentRequest();
}

async function deleteCurrentRequest() {
  if (!activeRequestId) return;
  if (!confirm("Are you sure you want to delete this request?")) return;
  try {
    await ApiService.deleteRequest(activeRequestId);
    activeRequestId = null;
    showNoSelection();
    if (activeProjectId) {
      loadProjectRequests(activeProjectId);
    }
    showToast("Request deleted");
  } catch (err) {
    console.error("Failed to delete request", err);
  }
}

// Key-Value Table Helpers
function populateKvTable(tbodyId, items) {
  const tbody = document.getElementById(tbodyId);
  tbody.innerHTML = "";
  if (!items || items.length === 0) {
    addKvRow(tbodyId);
    return;
  }
  items.forEach(item => addKvRow(tbodyId, item.key, item.value, item.enabled !== false));
}

function addKvRow(tbodyId, key = "", value = "", enabled = true) {
  const tbody = document.getElementById(tbodyId);
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td style="text-align: center;"><input type="checkbox" ${enabled ? 'checked' : ''} onchange="autoSaveCurrentRequest()"></td>
    <td><input type="text" placeholder="Key" value="${escapeHtml(key)}" onchange="autoSaveCurrentRequest()"></td>
    <td><input type="text" placeholder="Value" value="${escapeHtml(value)}" onchange="autoSaveCurrentRequest()"></td>
    <td>
      <button class="btn-icon" title="Remove" onclick="this.closest('tr').remove(); autoSaveCurrentRequest();">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    </td>
  `;
  tbody.appendChild(tr);
}

function readKvTable(tbodyId) {
  const rows = document.querySelectorAll(`#${tbodyId} tr`);
  const result = [];
  rows.forEach(r => {
    const checkbox = r.querySelector('input[type="checkbox"]');
    const inputs = r.querySelectorAll('input[type="text"]');
    if (inputs.length >= 2) {
      const k = inputs[0].value.trim();
      const v = inputs[1].value.trim();
      if (k || v) {
        result.push({
          key: k,
          value: v,
          enabled: checkbox ? checkbox.checked : true
        });
      }
    }
  });
  return result;
}

// Tab Switching
function switchReqTab(tabName) {
  document.querySelectorAll(".request-builder .tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".request-builder .tab-pane").forEach(p => p.classList.remove("active"));

  const targetPane = document.getElementById(`tab-${tabName}`);
  if (targetPane) targetPane.classList.add("active");
  event.target.classList.add("active");
}

function toggleBodyType(type) {
  document.getElementById("bodyTypeNone").style.display = type === "none" ? "block" : "none";
  document.getElementById("bodyTypeJson").style.display = type === "raw_json" ? "block" : "none";
  document.getElementById("bodyTypeFormData").style.display = type === "form_data" ? "block" : "none";
  autoSaveCurrentRequest();
}

function beautifyJsonBody() {
  const area = document.getElementById("bodyRawJson");
  try {
    const parsed = JSON.parse(area.value);
    area.value = JSON.stringify(parsed, null, 2);
    autoSaveCurrentRequest();
    showToast("JSON formatted");
  } catch (e) {
    alert("Invalid JSON: " + e.message);
  }
}

function switchRespTab(tabName) {
  document.querySelectorAll(".response-header .tab-btn").forEach(b => b.classList.remove("active"));
  event.target.classList.add("active");

  document.getElementById("resp-tab-body").style.display = tabName === "body" ? "block" : "none";
  document.getElementById("resp-tab-headers").style.display = tabName === "headers" ? "block" : "none";
}

// Request Execution
function handleUrlKeydown(e) {
  if (e.key === "Enter") {
    e.preventDefault();
    runRequest();
  }
}

async function runRequest() {
  const btn = document.getElementById("btnRun");
  const reqData = getFormDataFromUi();
  reqData.project_id = activeProjectId;

  const proj = projects.find(p => p.id === activeProjectId);
  if (proj) reqData.base_url = proj.base_url;

  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> <span>Running...</span>`;

  const metricsEl = document.getElementById("responseMetrics");
  metricsEl.innerHTML = `<span style="color: var(--text-muted);">Executing HTTP request...</span>`;

  try {
    const data = await ApiService.executeRequest(reqData);
    renderResponse(data);
  } catch (err) {
    metricsEl.innerHTML = `<span class="status-badge status-0">Error</span>`;
    document.getElementById("responseBodyDisplay").textContent = "Request execution failed: " + err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>Run</span>`;
  }
}

function renderResponse(res) {
  const metricsEl = document.getElementById("responseMetrics");
  const bodyEl = document.getElementById("responseBodyDisplay");
  const headersTbody = document.getElementById("respHeadersTableBody");
  const headersCountEl = document.getElementById("respHeadersCount");

  let statusClass = "status-0";
  const code = res.status_code || 0;
  if (code >= 200 && code < 300) statusClass = "status-2xx";
  else if (code >= 300 && code < 400) statusClass = "status-3xx";
  else if (code >= 400 && code < 500) statusClass = "status-4xx";
  else if (code >= 500) statusClass = "status-5xx";

  const sizeStr = res.size_bytes !== undefined ? formatBytes(res.size_bytes) : "0 B";
  const durationStr = res.duration_ms !== undefined ? `${res.duration_ms} ms` : "0 ms";

  metricsEl.innerHTML = `
    <span class="status-badge ${statusClass}">${code} ${escapeHtml(res.status_text || '')}</span>
    <span style="color: #60a5fa;" title="Response Duration">⚡ ${durationStr}</span>
    <span style="color: #94a3b8;" title="Response Size">📦 ${sizeStr}</span>
  `;

  if (res.error) {
    currentRawResponse = res.error;
    bodyEl.innerHTML = `<span style="color: #f87171;">${escapeHtml(res.error)}</span>`;
  } else if (res.is_json && res.body !== null) {
    currentRawResponse = JSON.stringify(res.body, null, 2);
    bodyEl.innerHTML = syntaxHighlightJson(currentRawResponse);
  } else {
    currentRawResponse = res.raw_text || "";
    bodyEl.textContent = currentRawResponse || "(Empty Response Body)";
  }

  headersTbody.innerHTML = "";
  if (res.headers && res.headers.length > 0) {
    headersCountEl.textContent = `(${res.headers.length})`;
    res.headers.forEach(h => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="color: #93c5fd; font-family: var(--font-mono); font-size: 0.8rem;">${escapeHtml(h.key)}</td>
        <td style="font-family: var(--font-mono); font-size: 0.8rem; word-break: break-all;">${escapeHtml(h.value)}</td>
      `;
      headersTbody.appendChild(tr);
    });
  } else {
    headersCountEl.textContent = "";
    headersTbody.innerHTML = `<tr><td colspan="2" style="color: var(--text-muted); padding: 12px;">No response headers received.</td></tr>`;
  }
}

function copyResponseBody() {
  if (!currentRawResponse) return;
  navigator.clipboard.writeText(currentRawResponse);
  showToast("Response copied to clipboard");
}

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function syntaxHighlightJson(jsonStr) {
  jsonStr = escapeHtml(jsonStr);
  return jsonStr.replace(/("(\\\\u[a-zA-Z0-9]{4}|\\\\[^u]|[^\\\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g, function (match) {
    let cls = 'json-number';
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        cls = 'json-key';
      } else {
        cls = 'json-string';
      }
    } else if (/true|false/.test(match)) {
      cls = 'json-boolean';
    } else if (/null/.test(match)) {
      cls = 'json-null';
    }
    return '<span class="' + cls + '">' + match + '</span>';
  });
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Modal Handlers
function openNewProjectModal() {
  document.getElementById("projectNameInput").value = "";
  document.getElementById("projectBaseUrlInput").value = "";
  document.getElementById("projectModal").classList.add("show");
  document.getElementById("projectNameInput").focus();
}

function closeProjectModal() {
  document.getElementById("projectModal").classList.remove("show");
}

async function submitProjectModal() {
  const name = document.getElementById("projectNameInput").value.trim();
  const baseUrl = document.getElementById("projectBaseUrlInput").value.trim();
  if (!name) {
    alert("Please enter a project name.");
    return;
  }

  try {
    const newProj = await ApiService.createProject(name, baseUrl);
    closeProjectModal();
    await loadProjects();
    selectProject(newProj.id);
    switchMainView('client');
    showToast("Project created");
  } catch (err) {
    console.error("Failed to create project", err);
  }
}

function openImportModal() {
  document.getElementById("importFileInput").value = "";
  document.getElementById("importJsonInput").value = "";
  document.getElementById("importModal").classList.add("show");
  document.getElementById("importJsonInput").focus();
}

function closeImportModal() {
  document.getElementById("importModal").classList.remove("show");
}

function handleImportFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(evt) {
    document.getElementById("importJsonInput").value = evt.target.result;
  };
  reader.readAsText(file);
}

async function submitImport() {
  const text = document.getElementById("importJsonInput").value.trim();
  if (!text) {
    alert("Please select a file or paste JSON collection text.");
    return;
  }

  let parsedData = null;
  try {
    parsedData = JSON.parse(text);
  } catch (e) {
    alert("Invalid JSON format: " + e.message);
    return;
  }

  const btn = document.getElementById("btnSubmitImport");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Importing...`;

  try {
    const data = await ApiService.importCollection(parsedData);
    if (data.error) {
      alert("Import failed: " + data.error);
    } else {
      closeImportModal();
      await loadProjects();
      if (data.project && data.project.id) {
        selectProject(data.project.id);
      }
      switchMainView('client');
      showToast(`Imported "${data.project.name}" (${data.imported_count} requests)`);
    }
  } catch (err) {
    alert("Import request error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = "Import Collection";
  }
}
