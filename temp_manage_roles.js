
const TOKEN = localStorage.getItem("admin_token");
const API   = window.API_BASE || "";

// --- ADMIN STAFF MANAGEMENT JS ---
async function fetchAdmins() {
  try {
    const res = await fetch(`${API}/admin-panel/admins`, {
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (!res.ok) throw new Error(await res.text());
    const admins = await res.json();
    adminsList = admins;
    renderStaffStats(admins);
    renderAdmins(admins);
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

    const recentLogs = data.recent_logs || [];
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
fetchRoles();

