
const TOKEN = localStorage.getItem("admin_token");
const API   = window.API_BASE || "";

// ─── ALL ADMIN MODULES ───────────────────────────────────────
const MODULES = [
  { key: "User Management",                   icon: "fa-users" },
  { key: "Subscription Plans & Transactions", icon: "fa-credit-card" },
  { key: "Schools",                           icon: "fa-building" },
  { key: "Questions Base",                    icon: "fa-question-circle" },
  { key: "Exams, Textbooks & Syllabus",       icon: "fa-file-text" },
  { key: "Quizzes",                           icon: "fa-pencil-square-o" },
  { key: "Games",                             icon: "fa-gamepad" },
  { key: "Tutorials",                         icon: "fa-youtube-play" },
  { key: "Notifications",                     icon: "fa-bell" },
  { key: "Analytics",                         icon: "fa-bar-chart" },
  { key: "Special Days",                      icon: "fa-calendar" },
  { key: "Social Content & Contributors",     icon: "fa-share-alt" },
  { key: "AI Usage",                          icon: "fa-microchip" },
  { key: "Roles & Permissions",               icon: "fa-shield" }
];

const ACTIONS = ["read", "create", "update", "delete"];

let roles = [];
let selectedRole = null;
let editingRoleName = null;
let adminsList = [];
let adminDetailsUsername = null;
let roleSearchQuery = "";
let roleMonitorLogs = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function countPermissions(permissionMap = {}) {
  return ACTIONS.reduce((total, action) => {
    return total + MODULES.reduce((moduleTotal, module) => {
      const modulePerms = permissionMap[module.key] || {};
      return moduleTotal + (modulePerms[action] ? 1 : 0);
    }, 0);
  }, 0);
}

function getConfiguredRoleCount() {
  return roles.filter(role => countPermissions(role.permissions || {}) > 0).length;
}

function normalizeStatus(status) {
  if (!status) return "success";
  if (status === "completed") return "success";
  return status;
}

function isRoleRelatedLog(log = {}) {
  const action = String(log.action || "").toLowerCase();
  const details = String(log.details || "").toLowerCase();
  return action.includes("role") || action.includes("permission") || details.includes("role") || details.includes("permission");
}

function getModuleSummary(moduleName) {
  const map = {
    "User Management": "Manage admin and user records.",
    "Subscription Plans & Transactions": "Control billing, plans, and payments.",
    "Schools": "Handle school records and access.",
    "Questions Base": "Create and maintain question banks.",
    "Exams, Textbooks & Syllabus": "Manage exam and content modules.",
    "Quizzes": "Run quiz content and settings.",
    "Games": "Control gamified learning experiences.",
    "Tutorials": "Manage tutorial content and publishing.",
    "Notifications": "Send alerts and system messages.",
    "Analytics": "View dashboards and usage reports.",
    "Special Days": "Configure seasonal or event content.",
    "Social Content & Contributors": "Moderate social and contributor content.",
    "AI Usage": "Inspect AI usage and cost impact.",
    "Roles & Permissions": "Manage access rules for roles."
  };
  return map[moduleName] || "Module access and settings.";
}

function getModuleTone(index) {
  return ["teal", "sky", "slate"][index % 3];
}

async function fetchRoles() {
  try {
    const res = await fetch(`${API}/admin-panel/roles`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw new Error(await res.text());

    const result = await res.json();
    roles = Array.isArray(result) ? result : [];
    if (selectedRole) {
      selectedRole = roles.find(role => role.role_name === selectedRole.role_name) || null;
    }
    renderRolesList();
    updateRoleKpis();
  } catch (e) {
    document.getElementById("roles-list").innerHTML = `
      <div class="empty-state">
        <i class="fa fa-exclamation-triangle" style="color:#e53e3e"></i>
        <p>Failed to load roles.<br><small>${e.message}</small></p>
      </div>`;
  }
}

function updateRoleKpis() {
  document.getElementById("roles-total-count").textContent = roles.length;
  document.getElementById("roles-configured-count").textContent = getConfiguredRoleCount();
  document.getElementById("roles-failed-count").textContent = roleMonitorLogs.filter(log => normalizeStatus(log.status) === "failed").length;
}

function renderRolesList() {
  const el = document.getElementById("roles-list");
  const filteredRoles = roles.filter(role => {
    if (!roleSearchQuery) return true;
    const name = String(role.role_name || "").toLowerCase();
    const desc = String(role.description || "").toLowerCase();
    return name.includes(roleSearchQuery) || desc.includes(roleSearchQuery);
  });

  if (!filteredRoles.length) {
    if (roles.length) {
      el.innerHTML = `
        <div class="empty-state">
          <i class="fa fa-search"></i>
          <p>No roles match your search.</p>
        </div>`;
    } else {
      el.innerHTML = `<div class="empty-state"><i class="fa fa-folder-open-o"></i><p>No roles yet. Create your first role!</p></div>`;
    }
    document.getElementById("permissions-body").innerHTML = `
      <div class="empty-state">
        <i class="fa fa-mouse-pointer"></i>
        <p>Select a role from the left panel to view and edit its module permissions.</p>
      </div>`;
    document.getElementById("selected-role-badge").textContent = "Select a role ->";
    document.getElementById("selected-role-meta").textContent = "Select a role to inspect its permission matrix.";
    updatePermissionMetrics(null);
    return;
  }

  if (!roles.length) {
    el.innerHTML = `<div class="empty-state"><i class="fa fa-folder-open-o"></i><p>No roles yet. Create your first role!</p></div>`;
    document.getElementById("permissions-body").innerHTML = `
      <div class="empty-state">
        <i class="fa fa-mouse-pointer"></i>
        <p>Select a role from the left panel to view and edit its module permissions.</p>
      </div>`;
    document.getElementById("selected-role-badge").textContent = "Select a role ->";
    document.getElementById("selected-role-meta").textContent = "Select a role to inspect its permission matrix.";
    updatePermissionMetrics(null);
    return;
  }

  el.innerHTML = filteredRoles.map(r => `
    <div class="role-item ${selectedRole && selectedRole.role_name === r.role_name ? "active" : ""}"
         onclick="selectRole(${JSON.stringify(r.role_name)})">
      <div>
        <div class="role-item-name">${escapeHtml(r.role_name)}</div>
        <div class="role-item-desc">${escapeHtml(r.description || "No description")}</div>
      </div>
      <div class="role-actions">
        <button class="btn-icon edit" title="Edit role info" onclick="event.stopPropagation(); openEditModal(${JSON.stringify(r.role_name)})">
          <i class="fa fa-pencil"></i>
        </button>
        <button class="btn-icon delete" title="Delete role" onclick="event.stopPropagation(); deleteRole(${JSON.stringify(r.role_name)})">
          <i class="fa fa-trash"></i>
        </button>
      </div>
    </div>`).join("");

  if (selectedRole) {
    renderPermissionsEditor();
  } else {
    updatePermissionMetrics(null);
  }
}

function selectRole(roleName) {
  selectedRole = roles.find(r => r.role_name === roleName) || null;
  renderRolesList();
  renderPermissionsEditor();
  updateRoleKpis();
}

function renderPermissionsEditor() {
  if (!selectedRole) return;

  const permissions = selectedRole.permissions || {};
  const moduleCount = MODULES.length;
  const readCount = MODULES.reduce((count, module) => count + ((permissions[module.key] || {}).read ? 1 : 0), 0);
  const writeCount = MODULES.reduce((count, module) => {
    const modulePerms = permissions[module.key] || {};
    return count + (modulePerms.create ? 1 : 0) + (modulePerms.update ? 1 : 0) + (modulePerms.delete ? 1 : 0);
  }, 0);
  const totalActions = countPermissions(permissions);

  document.getElementById("selected-role-badge").textContent = selectedRole.role_name;
  document.getElementById("selected-role-meta").textContent = `${escapeHtml(selectedRole.description || "No description provided")} • ${totalActions} enabled actions`;
  document.getElementById("metric-modules").textContent = moduleCount;
  document.getElementById("metric-read").textContent = readCount;
  document.getElementById("metric-write").textContent = writeCount;
  document.getElementById("metric-total").textContent = totalActions;

  const rows = MODULES.map((m, idx) => {
    const mPerms = permissions[m.key] || {};
    const checkboxes = ACTIONS.map(a => `
      <td class="perm-check">
        <input type="checkbox" data-mod="${idx}" data-action="${a}" ${mPerms[a] ? "checked" : ""}>
      </td>
    `).join("");

    return `
      <tr>
        <td><span class="module-name"><i class="fa ${m.icon} module-icon"></i>${m.key}</span></td>
        ${checkboxes}
      </tr>`;
  }).join("");

  document.getElementById("permissions-body").innerHTML = `
    <div style="overflow-x:auto">
      <table class="table table-bordered table-striped mb-0">
        <colgroup>
          <col style="width:55%">
          <col style="width:12%">
          <col style="width:12%">
          <col style="width:12%">
          <col style="width:9%">
        </colgroup>
        <thead>
          <tr>
            <th>Module</th>
            <th style="text-align:center">Read</th>
            <th style="text-align:center">Create</th>
            <th style="text-align:center">Update</th>
            <th style="text-align:center">Delete</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="permissions-footer">
      <button class="btn-save-perms" onclick="savePermissions()">
        <i class="fa fa-save"></i> Save Permissions
      </button>
    </div>`;
}

function renderPermissionsEditor() {
  if (!selectedRole) return;

  const permissions = selectedRole.permissions || {};
  const moduleCount = MODULES.length;
  const readCount = MODULES.reduce((count, module) => count + ((permissions[module.key] || {}).read ? 1 : 0), 0);
  const writeCount = MODULES.reduce((count, module) => {
    const modulePerms = permissions[module.key] || {};
    return count + (modulePerms.create ? 1 : 0) + (modulePerms.update ? 1 : 0) + (modulePerms.delete ? 1 : 0);
  }, 0);
  const totalActions = countPermissions(permissions);

  document.getElementById("selected-role-badge").textContent = selectedRole.role_name;
  document.getElementById("selected-role-meta").textContent = `${selectedRole.description || "No description provided"} · ${totalActions} enabled actions`;
  document.getElementById("metric-modules").textContent = moduleCount;
  document.getElementById("metric-read").textContent = readCount;
  document.getElementById("metric-write").textContent = writeCount;
  document.getElementById("metric-total").textContent = totalActions;

  const cards = MODULES.map((m, idx) => {
    const mPerms = permissions[m.key] || {};
    const enabledCount = ACTIONS.reduce((count, action) => count + (mPerms[action] ? 1 : 0), 0);
    return `
      <article class="permission-card">
        <div class="permission-card-top">
          <div class="permission-card-title">
            <div class="permission-card-icon ${getModuleTone(idx)}">
              <i class="fa ${m.icon}"></i>
            </div>
            <div>
              <h4 class="permission-card-name">${escapeHtml(m.key)}</h4>
              <p class="permission-card-desc">${escapeHtml(getModuleSummary(m.key))}</p>
            </div>
          </div>
          <div class="permission-chip-row">
            <button class="permission-chip" type="button" onclick="toggleModulePermissions(${idx}, true)">
              <i class="fa fa-check"></i> All on
            </button>
            <button class="permission-chip" type="button" onclick="toggleModulePermissions(${idx}, false)">
              <i class="fa fa-ban"></i> Clear
            </button>
          </div>
        </div>
        <div class="permission-card-body">
          <div class="permission-action-grid">
            ${ACTIONS.map(action => `
              <div class="permission-toggle">
                <div>
                  <label for="perm-${idx}-${action}">${action}</label>
                  <small>${action === "read" ? "View access" : action === "create" ? "Add records" : action === "update" ? "Edit records" : "Remove records"}</small>
                </div>
                <input id="perm-${idx}-${action}" type="checkbox" data-mod="${idx}" data-action="${action}" ${mPerms[action] ? "checked" : ""}>
              </div>
            `).join("")}
          </div>
          <div class="mt-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
            <small class="text-muted">Enabled actions: ${enabledCount} / 4</small>
            <small class="text-muted">${mPerms.read ? "Visible" : "Hidden"} in this role</small>
          </div>
        </div>
      </article>`;
  }).join("");

  document.getElementById("permissions-body").innerHTML = `
    <div class="permission-hero">
      <div class="permission-hero-card">
        <div>
          <h6>${escapeHtml(selectedRole.role_name)}</h6>
          <p>${escapeHtml(selectedRole.description || "No description provided")} · Keep only the permissions this role should actually use.</p>
        </div>
        <div class="permission-legend">
          <span><i class="fa fa-eye"></i> Read</span>
          <span><i class="fa fa-plus"></i> Create</span>
          <span><i class="fa fa-pencil"></i> Update</span>
          <span><i class="fa fa-trash"></i> Delete</span>
        </div>
      </div>
    </div>
    <div class="permission-grid">
      ${cards}
    </div>
    <div class="permission-foot">
      <button class="btn-save-perms" onclick="savePermissions()">
        <i class="fa fa-save"></i> Save Permissions
      </button>
    </div>`;
}

function toggleModulePermissions(moduleIndex, enabled) {
  document.querySelectorAll(`#permissions-body input[data-mod="${moduleIndex}"]`).forEach(input => {
    input.checked = enabled;
  });
}

async function savePermissions() {
  if (!selectedRole) return;

  const permissions = {};
  document.querySelectorAll("#permissions-body input[data-mod]").forEach(cb => {
    const modIdx = parseInt(cb.getAttribute("data-mod"), 10);
    const action = cb.getAttribute("data-action");
    const modKey = MODULES[modIdx].key;
    if (!permissions[modKey]) permissions[modKey] = {};
    permissions[modKey][action] = cb.checked;
  });

  try {
    const res = await fetch(`${API}/admin-panel/roles/${encodeURIComponent(selectedRole.role_name)}/permissions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
      body: JSON.stringify({ permissions })
    });
    if (!res.ok) throw new Error(await res.text());

    selectedRole.permissions = permissions;
    roles = roles.map(r => r.role_name === selectedRole.role_name ? { ...r, permissions } : r);
    showToast("Permissions saved successfully!", "success");
    renderRolesList();
    updateRoleKpis();
    await fetchRoleMonitoring();
  } catch (e) {
    showToast("Failed to save: " + e.message, "error");
  }
}

function openCreateModal() {
  editingRoleName = null;
  document.getElementById("modal-title").textContent = "Create New Role";
  document.getElementById("input-role-name").value = "";
  document.getElementById("input-role-desc").value = "";
  document.getElementById("input-role-name").disabled = false;
  document.getElementById("roleModal").classList.add("show");
}

function openEditModal(roleName) {
  const r = roles.find(x => x.role_name === roleName);
  if (!r) {
    showToast("Role not found", "error");
    return;
  }

  editingRoleName = roleName;
  document.getElementById("modal-title").textContent = "Edit Role";
  document.getElementById("input-role-name").value = r.role_name;
  document.getElementById("input-role-desc").value = r.description || "";
  document.getElementById("input-role-name").disabled = true;
  document.getElementById("roleModal").classList.add("show");
}

function closeModal() {
  document.getElementById("roleModal").classList.remove("show");
}

async function submitRole() {
  const name = document.getElementById("input-role-name").value.trim();
  const desc = document.getElementById("input-role-desc").value.trim();

  if (!name) {
    showToast("Role name is required", "error");
    return;
  }

  try {
    if (editingRoleName) {
      const existing = roles.find(r => r.role_name === editingRoleName) || {};
      const res = await fetch(`${API}/admin-panel/roles/${encodeURIComponent(editingRoleName)}/permissions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
        body: JSON.stringify({ permissions: existing.permissions || {}, description: desc })
      });
      if (!res.ok) throw new Error(await res.text());
      showToast("Role updated!", "success");
    } else {
      const res = await fetch(`${API}/admin-panel/roles`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
        body: JSON.stringify({ role_name: name, description: desc, permissions: {} })
      });
      if (!res.ok) throw new Error(await res.text());
      showToast("Role created!", "success");
    }

    closeModal();
    await fetchRoles();
    await fetchRoleMonitoring();
  } catch (e) {
    showToast("Error: " + e.message, "error");
  }
}

async function deleteRole(roleName) {
  if (!confirm(`Delete role "${roleName}"? This cannot be undone.`)) return;

  try {
    const res = await fetch(`${API}/admin-panel/roles/${encodeURIComponent(roleName)}`, {
      method: "DELETE",
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Delete failed");
    }

    if (selectedRole && selectedRole.role_name === roleName) {
      selectedRole = null;
      document.getElementById("permissions-body").innerHTML = `
        <div class="empty-state">
          <i class="fa fa-mouse-pointer"></i>
          <p>Select a role from the left panel to view and edit its module permissions.</p>
        </div>`;
      document.getElementById("selected-role-badge").textContent = "Select a role ->";
      document.getElementById("selected-role-meta").textContent = "Select a role to inspect its permission matrix.";
      updatePermissionMetrics(null);
    }

    showToast("Role deleted.", "success");
    await fetchRoles();
    await fetchRoleMonitoring();
  } catch (e) {
    showToast(e.message, "error");
  }
}

function updatePermissionMetrics(selected) {
  if (!selected) {
    document.getElementById("metric-modules").textContent = "0";
    document.getElementById("metric-read").textContent = "0";
    document.getElementById("metric-write").textContent = "0";
    document.getElementById("metric-total").textContent = "0";
    return;
  }

  const permissions = selected.permissions || {};
  document.getElementById("metric-modules").textContent = MODULES.length;
  document.getElementById("metric-read").textContent = MODULES.reduce((count, module) => count + ((permissions[module.key] || {}).read ? 1 : 0), 0);
  document.getElementById("metric-write").textContent = MODULES.reduce((count, module) => {
    const modulePerms = permissions[module.key] || {};
    return count + (modulePerms.create ? 1 : 0) + (modulePerms.update ? 1 : 0) + (modulePerms.delete ? 1 : 0);
  }, 0);
  document.getElementById("metric-total").textContent = countPermissions(permissions);
}

function formatMonitorTime(timestamp) {
  try {
    return new Date(timestamp).toLocaleString();
  } catch {
    return "Unknown time";
  }
}

function renderRoleMonitoring(logs) {
  const el = document.getElementById("role-monitor-list");
  if (!logs.length) {
    el.innerHTML = `
      <div class="staff-empty" style="margin: 0;">
        <i class="fa fa-rss"></i>
        <div class="fw-bold">No role activity yet</div>
        <div class="mt-1">Role changes, permission updates, and failed attempts will appear here.</div>
      </div>`;
    return;
  }

  el.innerHTML = logs.slice(0, 8).map(log => {
    const status = normalizeStatus(log.status);
    return `
      <article class="monitor-item">
        <div class="monitor-item-top">
          <div>
            <p class="monitor-item-title">@${escapeHtml(log.username || "unknown")}</p>
            <p class="monitor-item-sub">${escapeHtml(log.action || "activity")}<br>${escapeHtml(log.details || "")}</p>
          </div>
          <span class="status-pill ${status === "failed" ? "failed" : status === "pending" ? "pending" : "success"}">${status}</span>
        </div>
        <div class="monitor-item-meta">
          <span>${escapeHtml(log.role || "staff")}</span>
          <span>${formatMonitorTime(log.timestamp)}</span>
        </div>
      </article>`;
  }).join("");
}

async function fetchRoleMonitoring() {
  const el = document.getElementById("role-monitor-list");
  el.innerHTML = `
    <div class="staff-loading" style="min-height:220px;">
      <div class="text-center">
        <div class="spinner-border text-secondary mb-2" role="status"></div>
        <div>Loading live role monitoring...</div>
      </div>
    </div>`;

  try {
    const res = await fetch(`${API}/admin-panel/stats/staff-activity`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw new Error(await res.text());

    const result = await res.json();
    const data = result.data || {};
    const logs = (data.recent_logs || []).filter(isRoleRelatedLog);
    roleMonitorLogs = logs;
    document.getElementById("monitor-total-events").textContent = logs.length;
    document.getElementById("monitor-failed-events").textContent = logs.filter(log => normalizeStatus(log.status) === "failed").length;
    updateRoleKpis();
    renderRoleMonitoring(logs);
  } catch (e) {
    el.innerHTML = `
      <div class="staff-empty text-danger" style="margin: 0;">
        <i class="fa fa-exclamation-triangle"></i>
        <div class="fw-bold">Failed to load monitoring</div>
        <div><small>${escapeHtml(e.message)}</small></div>
      </div>`;
  }
}

function showToast(msg, type = "success") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `toast-msg ${type} show`;
  setTimeout(() => t.classList.remove("show"), 3500);
}

document.getElementById("roleModal").addEventListener("click", function(e) {
  if (e.target === this) closeModal();
});
document.getElementById("adminModal").addEventListener("click", function(e) {
  if (e.target === this) closeAdminModal();
});
document.getElementById("adminDetailsModal").addEventListener("click", function(e) {
  if (e.target === this) closeAdminDetailsModal();
});

// --- ADMIN STAFF MANAGEMENT JS ---
async function fetchAdmins() {
  try {
    const res = await fetch(`${API}/admin-panel/admins`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw new Error(await res.text());
    const admins = await res.json();
    const safeAdmins = Array.isArray(admins) ? admins : [];
    adminsList = safeAdmins;
    renderStaffStats(safeAdmins);
    renderAdmins(safeAdmins);
  } catch (e) {
    document.getElementById("admins-list-body").innerHTML = `
      <div class="staff-empty text-danger">
        <i class="fa fa-exclamation-triangle"></i>
        <div class="fw-bold">Failed to load admin list</div>
        <div><small>${e.message}</small></div>
      </div>`;
  }
}

function renderStaffStats(admins) {
  document.getElementById("staff-stat-total").textContent = admins.length;
  document.getElementById("staff-stat-superadmins").textContent = admins.filter(a => (a.role_name || "superadmin") === "superadmin").length;
  document.getElementById("staff-stat-roles").textContent = new Set(admins.map(a => a.role_name || "superadmin")).size;
}

function renderAdmins(admins) {
  const el = document.getElementById("admins-list-body");
  if (!admins.length) {
    el.innerHTML = `
      <div class="staff-empty">
        <i class="fa fa-users"></i>
        <div class="fw-bold">No admin staff registered yet</div>
        <div class="mt-1">Create the first staff account to get started.</div>
      </div>`;
    return;
  }

  el.innerHTML = admins.map(admin => {
    const roleName = admin.role_name || "superadmin";
    const isSuperAdmin = roleName === "superadmin";
    const displayRole = roleName.charAt(0).toUpperCase() + roleName.slice(1);
    const initials = (admin.full_name || admin.username || "?")
      .split(" ")
      .map(part => part.charAt(0))
      .join("")
      .slice(0, 2)
      .toUpperCase();

    return `
      <article class="staff-card">
        <div class="staff-card-top">
          <div class="staff-profile">
            <div class="staff-avatar">${initials}</div>
            <div>
              <h4 class="staff-name">${admin.full_name || admin.username}</h4>
              <div class="staff-username">@${admin.username}</div>
            </div>
          </div>
          <span class="staff-role-badge ${isSuperAdmin ? "superadmin" : "staff"}">
            <i class="fa ${isSuperAdmin ? "fa-crown" : "fa-user"}"></i>
            ${displayRole}
          </span>
        </div>

        <div class="staff-details">
          <div class="staff-detail-row"><span>Email</span><span>${admin.email || "No email"}</span></div>
          <div class="staff-detail-row"><span>Phone</span><span>${admin.phone_number || "No phone"}</span></div>
          <div class="staff-detail-row"><span>Address</span><span>${admin.address || "No address"}</span></div>
        </div>

        <div class="staff-actions">
          <button class="staff-action-btn view" onclick='openViewAdminModal(${JSON.stringify(admin.username)})'><i class="fa fa-eye"></i> View</button>
          <button class="staff-action-btn edit" onclick='openEditAdminModal(${JSON.stringify(admin.username)})'><i class="fa fa-pencil"></i> Edit</button>
          <button class="staff-action-btn delete" onclick='deleteAdmin(${JSON.stringify(admin.username)})'><i class="fa fa-trash"></i> Delete</button>
        </div>
      </article>`;
  }).join("");
}

function openAdminModal() {
  const select = document.getElementById("admin-role-select");
  select.innerHTML = '<option value="superadmin">Superadmin (All Permissions)</option>' + roles.map(r => `<option value="${r.role_name}">${r.role_name}</option>`).join("");
  document.getElementById("admin-fullname").value = "";
  document.getElementById("admin-email").value = "";
  document.getElementById("admin-phone").value = "";
  document.getElementById("admin-address").value = "";
  document.getElementById("admin-username").value = "";
  document.getElementById("admin-password").value = "";
  document.getElementById("adminModal").classList.add("show");
}

function closeAdminModal() {
  document.getElementById("adminModal").classList.remove("show");
}

function getAdminByUsername(username) {
  return adminsList.find(a => a.username === username);
}

function populateAdminRoleSelect(selectedRole) {
  const select = document.getElementById("detail-admin-role-select");
  select.innerHTML = '<option value="superadmin">Superadmin (All Permissions)</option>' + roles.map(r => `<option value="${r.role_name}">${r.role_name}</option>`).join("");
  if (selectedRole) select.value = selectedRole;
}

function setAdminDetailsMode(mode) {
  const isView = mode === "view";
  document.getElementById("detail-admin-fullname").disabled = isView;
  document.getElementById("detail-admin-email").disabled = isView;
  document.getElementById("detail-admin-phone").disabled = isView;
  document.getElementById("detail-admin-address").disabled = isView;
  document.getElementById("detail-admin-role-select").disabled = isView;
  document.getElementById("detail-password-wrap").style.display = isView ? "none" : "block";
  document.getElementById("admin-details-save-btn").style.display = isView ? "none" : "inline-flex";
}

function fillAdminDetailsModal(admin) {
  document.getElementById("detail-admin-fullname").value = admin.full_name || "";
  document.getElementById("detail-admin-email").value = admin.email || "";
  document.getElementById("detail-admin-phone").value = admin.phone_number || "";
  document.getElementById("detail-admin-address").value = admin.address || "";
  document.getElementById("detail-admin-username").value = admin.username || "";
  document.getElementById("side-username").textContent = `@${admin.username || ""}`;
  document.getElementById("side-email").textContent = admin.email || "No email";
  document.getElementById("side-phone").textContent = admin.phone_number || "No phone";
  document.getElementById("side-address").textContent = admin.address || "No address";
  document.getElementById("side-role").textContent = admin.role_name || "superadmin";
  document.getElementById("detail-avatar").textContent = (admin.full_name || admin.username || "?")
    .split(" ")
    .map(part => part.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
  populateAdminRoleSelect(admin.role_name || "superadmin");
}

function openViewAdminModal(username) {
  const admin = getAdminByUsername(username);
  if (!admin) {
    showToast("Admin staff record not found", "error");
    return;
  }
  adminDetailsUsername = username;
  document.getElementById("admin-details-title").textContent = "View Admin Staff";
  document.getElementById("admin-details-main-title").textContent = "Staff Profile";
  document.getElementById("admin-details-subtitle").textContent = `Read-only details for @${username}`;
  fillAdminDetailsModal(admin);
  setAdminDetailsMode("view");
  document.getElementById("adminDetailsModal").classList.add("show");
}

function openEditAdminModal(username) {
  const admin = getAdminByUsername(username);
  if (!admin) {
    showToast("Admin staff record not found", "error");
    return;
  }
  adminDetailsUsername = username;
  document.getElementById("admin-details-title").textContent = "Edit Admin Staff";
  document.getElementById("admin-details-main-title").textContent = "Edit Staff Profile";
  document.getElementById("admin-details-subtitle").textContent = `Update details for @${username}`;
  fillAdminDetailsModal(admin);
  document.getElementById("detail-admin-password").value = "";
  setAdminDetailsMode("edit");
  document.getElementById("adminDetailsModal").classList.add("show");
}

function closeAdminDetailsModal() {
  document.getElementById("adminDetailsModal").classList.remove("show");
  adminDetailsUsername = null;
}

async function submitAdminDetails() {
  if (!adminDetailsUsername) return;
  const fullname = document.getElementById("detail-admin-fullname").value.trim();
  const email = document.getElementById("detail-admin-email").value.trim();
  const phone = document.getElementById("detail-admin-phone").value.trim();
  const address = document.getElementById("detail-admin-address").value.trim();
  const roleName = document.getElementById("detail-admin-role-select").value;
  const password = document.getElementById("detail-admin-password").value.trim();

  if (!fullname || !email || !phone || !address || !roleName) {
    showToast("All required fields must be filled", "error");
    return;
  }

  const payload = { full_name: fullname, email, phone_number: phone, address, role_name: roleName };
  if (password) payload.password = password;

  try {
    const res = await fetch(`${API}/admin-panel/admins/${encodeURIComponent(adminDetailsUsername)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Update failed");
    }
    showToast("Admin staff account updated!", "success");
    closeAdminDetailsModal();
    fetchAdmins();
  } catch (e) {
    showToast(e.message, "error");
  }
}

async function submitAdmin() {
  const fullname = document.getElementById("admin-fullname").value.trim();
  const email = document.getElementById("admin-email").value.trim();
  const phone = document.getElementById("admin-phone").value.trim();
  const address = document.getElementById("admin-address").value.trim();
  const username = document.getElementById("admin-username").value.trim();
  const password = document.getElementById("admin-password").value.trim();
  const roleName = document.getElementById("admin-role-select").value;

  if (!fullname || !email || !phone || !address || !username || !password) {
    showToast("All fields are required", "error");
    return;
  }
  if (password.length < 6) {
    showToast("Password must be at least 6 characters", "error");
    return;
  }

  try {
    const res = await fetch(`${API}/admin-panel/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
      body: JSON.stringify({ full_name: fullname, email, phone_number: phone, address, username, password, role_name: roleName })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Registration failed");
    }
    showToast("Admin staff account created!", "success");
    closeAdminModal();
    fetchAdmins();
  } catch (e) {
    showToast(e.message, "error");
  }
}

async function deleteAdmin(username) {
  if (!confirm(`Are you sure you want to delete staff account "${username}"?`)) return;
  try {
    const res = await fetch(`${API}/admin-panel/admins/${encodeURIComponent(username)}`, {
      method: "DELETE",
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Delete failed");
    }
    showToast("Admin staff account deleted", "success");
    fetchAdmins();
  } catch (e) {
    showToast(e.message, "error");
  }
}

async function fetchActivityLogs() {
  const leaderboardEl = document.getElementById("leaderboard-container");
  const logsBody = document.getElementById("activity-logs-body");
  const trendEl = document.getElementById("trend-container");

  leaderboardEl.innerHTML = `<div class="text-center py-4"><div class="spinner-border spinner-border-sm text-secondary"></div></div>`;
  logsBody.innerHTML = `<tr><td colspan="6" class="text-center py-5 text-muted"><div class="spinner-border text-secondary mb-2" role="status"></div><p class="mb-0">Retrieving staff activity logs...</p></td></tr>`;
  trendEl.innerHTML = `<div class="text-center py-4"><div class="spinner-border spinner-border-sm text-secondary"></div></div>`;

  try {
    const res = await fetch(`${API}/admin-panel/stats/staff-activity`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw new Error(await res.text());
    const result = await res.json();
    const data = result.data || {};

    const leaderboard = data.leaderboard || [];
    const recentLogs = data.recent_logs || [];
    const failedCount = recentLogs.filter(log => normalizeStatus(log.status) === "failed").length;

    document.getElementById("activity-total-events").textContent = recentLogs.length;
    document.getElementById("activity-failed-events").textContent = failedCount;
    document.getElementById("activity-top-user").textContent = leaderboard.length ? `@${leaderboard[0].username}` : "-";
    document.getElementById("activity-last-updated").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    if (!leaderboard.length) {
      leaderboardEl.innerHTML = `<p class="text-muted text-center py-3">No activity logs recorded yet.</p>`;
    } else {
      leaderboardEl.innerHTML = `
        <ul class="list-group list-group-flush">
          ${leaderboard.map((item, idx) => `
            <li class="list-group-item d-flex justify-content-between align-items-center py-2 px-1">
              <div>
                <span class="badge bg-primary me-2">${idx + 1}</span>
                <span class="fw-bold">@${item.username}</span>
              </div>
              <span class="badge rounded-pill bg-light text-primary fw-bold" style="font-size:0.75rem; color:#7366ff !important; background:rgba(115,102,255,0.1);">${item.count} actions</span>
            </li>
          `).join("")}
        </ul>`;
    }

    const dailyTrend = data.daily_trend || [];
    if (!dailyTrend.length) {
      trendEl.innerHTML = `<p class="text-muted text-center py-3">No daily activity records.</p>`;
    } else {
      trendEl.innerHTML = `
        <div style="overflow-x:auto;">
          <table class="table table-bordered table-striped mb-0 text-center">
            <thead>
              <tr>
                ${dailyTrend.map(item => `<th style="font-size: 0.8rem; padding: 8px;">${item.date.split('-').slice(1).join('/')}</th>`).join("")}
              </tr>
            </thead>
            <tbody>
              <tr>
                ${dailyTrend.map(item => `<td class="fw-bold text-primary" style="padding: 10px; font-size: 1.1rem;">${item.count}</td>`).join("")}
              </tr>
            </tbody>
          </table>
        </div>`;
    }

    if (!recentLogs.length) {
      logsBody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-muted py-4">No recent activity found.</td>
        </tr>`;
    } else {
      logsBody.innerHTML = recentLogs.map(log => `
        <tr>
          <td style="padding:12px 20px;"><strong>@${log.username}</strong></td>
          <td style="padding:12px 20px;"><span class="badge bg-soft-primary text-primary" style="background: rgba(115,102,255,0.08);">${log.role || "staff"}</span></td>
          <td style="padding:12px 20px;"><span class="text-primary fw-medium">${log.action}</span></td>
          <td style="padding:12px 20px;">
            <span class="badge ${log.status === "failed" ? "bg-danger" : log.status === "completed" ? "bg-success" : "bg-warning text-dark"}">
              ${log.status || "success"}
            </span>
          </td>
          <td style="padding:12px 20px;">${log.details || ""}</td>
          <td style="padding:12px 20px;"><small class="text-muted">${new Date(log.timestamp).toLocaleString()}</small></td>
        </tr>`).join("");
    }
  } catch (e) {
    leaderboardEl.innerHTML = `<p class="text-danger text-center">Error loading leaderboard</p>`;
    trendEl.innerHTML = `<p class="text-danger text-center">Error loading trend</p>`;
    logsBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">Failed to load activity logs: ${e.message}</td></tr>`;
  }
}

// --- INIT ---
const roleSearchInput = document.getElementById("role-search");
if (roleSearchInput) {
  roleSearchInput.addEventListener("input", (event) => {
    roleSearchQuery = event.target.value.trim().toLowerCase();
    renderRolesList();
  });
}

const rolesTab = document.getElementById("roles-tab");
if (rolesTab) {
  rolesTab.addEventListener("shown.bs.tab", () => {
    fetchRoles();
    fetchRoleMonitoring();
  });
}

fetchRoles();
fetchRoleMonitoring();
fetchActivityLogs();
