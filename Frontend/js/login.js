document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  const errorEl  = document.getElementById("error");

  try {
    const data = await apiFetch("/admin/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    });
    localStorage.setItem("admin_token", data.access_token);
    window.location.href = "dashboard.html";
  } catch (err) {
    errorEl.textContent = err.message;
  }
});
