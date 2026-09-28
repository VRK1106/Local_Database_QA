# Test Accounts & Access Credentials

Use these verified accounts to test each persona and role-based feature in the system.

| Role | Username | Password | Student ID | Scope & Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Student** | `stu001` | `Password@123` | `STU001` | **Zero-Trust Student Persona.** Access to personal placement profile, public circulars, personal support tickets. Strictly blocked from accessing other students' records or internal coordinator memos. |
| **Placement Coordinator (Admin)** | `admin` | `admin123` | *N/A* | **Placement Cell Staff Persona.** Access to batch analytics, document upload & visibility tagging (Public vs. Internal), student account password resets, isolated audit logs, and coordinator issue queue. |
| **Developer** | `dev_admin` | `DeveloperPass@1234` | *N/A* | **Full Engineering Persona.** Access to system telemetry, technical Q&A sliders, global audit trails, user role management, View-As impersonation, Danger Zone re-indexing, and developer ticket escalations. |

---

## Quick Reference: Testing URLs

- **Main Application & Q&A:** `http://127.0.0.1:5000/`
- **Login:** `http://127.0.0.1:5000/login`
- **Logout:** `http://127.0.0.1:5000/logout`
- **Issue Resolver (Tickets):** `http://127.0.0.1:5000/tickets`
- **Document Management:** `http://127.0.0.1:5000/documents`
- **Audit Logs:** `http://127.0.0.1:5000/audit_logs`
- **User Management (Placement):** `http://127.0.0.1:5000/admin/users`
- **Developer Dashboard:** `http://127.0.0.1:5000/dev/dashboard`
- **Developer Users:** `http://127.0.0.1:5000/dev/users`
- **Developer Danger Zone:** `http://127.0.0.1:5000/dev/danger`
- **Developer Config:** `http://127.0.0.1:5000/dev/config`
- **User Profile:** `http://127.0.0.1:5000/profile`
- **Settings:** `http://127.0.0.1:5000/settings`
