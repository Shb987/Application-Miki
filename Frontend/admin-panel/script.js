// Helper for API requests with JWT
async function apiRequest(url, method = "GET", body = null) {
  const token = localStorage.getItem("token");
  if (!token) {
    alert("Please login first!");
    window.location.href = "login.html";
    return;
  }

  const headers = { "Content-Type": "application/json", "Authorization": "Bearer " + token };

  const response = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (response.status === 401) {
    alert("Session expired. Please login again.");
    localStorage.removeItem("token");
    window.location.href = "login.html";
  }

  return await response.json();
}
