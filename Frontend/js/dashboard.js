async function loadStudents() {
  try {
    const students = await apiFetch("/user/all-students");
    const tbody = document.querySelector("#studentsTable tbody");
    tbody.innerHTML = "";

    if (students.length === 0) {
      tbody.innerHTML = "<tr><td colspan='7'>No students yet</td></tr>";
      return;
    }

    students.forEach(s => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${s.student_id || "-"}</td>
        <td>${s.student_name || "-"}</td>
        <td>${s.student_class || s.class_name || "-"}</td>
        <td>${s.guardian_name || "-"}</td>
        <td>${s.parent_mobile || s.parent_number || "-"}</td>
        <td>${s.dob || "-"}</td>
        <td>${s.address || "-"}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    alert("Error loading students: " + err.message);
  }
}

document.getElementById("logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("admin_token");
  window.location.href = "index.html";
});

loadStudents();
