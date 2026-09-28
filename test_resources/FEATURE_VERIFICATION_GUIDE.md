# End-to-End Feature Verification & Quality Assurance Manual

This guide provides instructions on how to verify that **every single feature** of the Local Database QA System is operational.

All necessary testing files, sample documents, test credentials, and automated runners are consolidated in this directory:
📁 **`test_resources/`**

---

## 📑 Table of Contents

1. [Test Credentials & Quick URLs](#1-test-credentials--quick-urls)
2. [Module 1: Three-Tier Authentication & Session Security](#2-module-1-three-tier-authentication--session-security)
3. [Module 2: UI Shell, Navigation & Sidebar Behavior](#3-module-2-ui-shell-navigation--sidebar-behavior)
4. [Module 3: Student Portal & Zero-Trust Isolation](#4-module-3-student-portal--zero-trust-isolation)
5. [Module 4: Placement Coordinator Portal & Administration](#5-module-4-placement-coordinator-portal--administration)
6. [Module 5: Developer Portal, Impersonation & Safeguards](#6-module-5-developer-portal-impersonation--safeguards)
7. [Module 6: Ticket-Based Issue Resolution Lifecycle](#7-module-6-ticket-based-issue-resolution-lifecycle)
8. [Module 7: Voice Typing & Dictation](#8-module-7-voice-typing--dictation)
9. [Module 8: Custom Error Handling Pages](#9-module-8-custom-error-handling-pages)
10. [Automated Verification Suite](#10-automated-verification-suite)

---

## 1. Test Credentials & Quick URLs

| Role | Username | Password | Student ID | Scope & Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Student** | `stu001` | `Password@123` | `STU001` | Student view. Access to personal placement profile, public circulars, own tickets. Blocked from aggregate peer statistics and internal staff memos. |
| **Placement Officer** | `admin` | `admin123` | *N/A* | Administrative placement view. Access to batch analytics, document upload/tagging, student account management, isolated audit logs. |
| **Developer** | `dev_admin` | `DeveloperPass@1234` | *N/A* | Engineering oversight. Access to system telemetry, technical sliders, global audit trails, user role management, View-As impersonation, Danger Zone. |

### Application Endpoints
- **Main Portal (Q&A):** `http://127.0.0.1:5000/`
- **Sign In:** `http://127.0.0.1:5000/login`
- **Issue Resolver (Tickets):** `http://127.0.0.1:5000/tickets`
- **Document Manager:** `http://127.0.0.1:5000/documents`
- **Audit Logs:** `http://127.0.0.1:5000/audit_logs`
- **User Management (Placement):** `http://127.0.0.1:5000/admin/users`
- **Developer Telemetry:** `http://127.0.0.1:5000/dev/dashboard`
- **Developer Danger Zone:** `http://127.0.0.1:5000/dev/danger`
- **Developer User Controls:** `http://127.0.0.1:5000/dev/users`
- **Student Profile:** `http://127.0.0.1:5000/profile`
- **User Settings:** `http://127.0.0.1:5000/settings`

---

## 2. Module 1: Three-Tier Authentication & Session Security

### Feature 1.1: Unauthenticated Route Protection
- **Objective:** Verify that private views cannot be accessed without logging in.
- **Manual Verification Steps:**
  1. Open a browser in Incognito / Private mode.
  2. Navigate directly to `http://127.0.0.1:5000/documents` or `http://127.0.0.1:5000/tickets`.
  3. **Expected Result:** The browser is immediately redirected to `/login`, and an info notification states: *"Please sign in to access the Local Database QA System."*

### Feature 1.2: Role-Based Sign In
- **Objective:** Confirm successful authentication and correct persona initialization.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/login`.
  2. Sign in with `stu001` / `Password@123`.
  3. **Expected Result:** Redirects to `/`. The top-right navbar displays a cyan badge: `STUDENT (STU001)`.
  4. Sign out (`http://127.0.0.1:5000/logout`) and sign in with `admin` / `admin123`.
  5. **Expected Result:** Top-right navbar displays a green badge: `PLACEMENT CELL`.

### Feature 1.3: Auto-Dismissing Flash Notifications
- **Objective:** Verify that login/action alert banners disappear automatically.
- **Manual Verification Steps:**
  1. Log in with any account.
  2. A green notification banner appears: *"Signed in successfully."*
  3. **Expected Result:** After exactly 3 seconds, the alert smoothly fades out and collapses from the layout without requiring manual close.

---

## 3. Module 2: UI Shell, Navigation & Sidebar Behavior

### Feature 2.1: Collapsible Auto-Hiding Sidebar
- **Objective:** Verify spacious UI layout with hover-activated side panel.
- **Manual Verification Steps:**
  1. Move the cursor away from the left edge. The sidebar is completely hidden/collapsed, leaving maximum screen space for Q&A and content.
  2. Hover your mouse over the hamburger icon (☰) at the top-left corner.
  3. **Expected Result:** The sidebar expands into view.
  4. Move your cursor away from the sidebar.
  5. **Expected Result:** The sidebar automatically hides.

### Feature 2.2: Forward / Back / Home Navigation Control Panel
- **Objective:** In-app browser history controls.
- **Manual Verification Steps:**
  1. Look at the top navigation bar next to the logo.
  2. Click the **Home (🏠)** button -> Navigates to `/`.
  3. Click **Issue Resolver** in sidebar -> Navigates to `/tickets`.
  4. Click the **Back (◀)** button -> Navigates back to `/`.
  5. Click the **Forward (▶)** button -> Navigates forward to `/tickets`.

### Feature 2.3: Real-Time Open Tickets Counter Badge
- **Objective:** Dynamic badge indication of active open issues.
- **Manual Verification Steps:**
  1. Hover over the sidebar and inspect the **Issue Resolver** nav item.
  2. **Expected Result:** If open tickets exist, a glowing badge displays the count of open issues.

---

## 4. Module 3: Student Portal & Zero-Trust Isolation

### Feature 3.1: Personalized Student Profile (`/profile`)
- **Objective:** Confirm live data extraction from official student records.
- **Manual Verification Steps:**
  1. Log in as `stu001` / `Password@123`.
  2. Click on the profile icon or go to `http://127.0.0.1:5000/profile`.
  3. **Expected Result:** Displays student record for **Aarav Patel**, Student ID: **STU001**, Department: **Computer Science & Engineering**, Current Status: **Not Placed**, Tech Score: **4/5**.

### Feature 3.2: Personal Parameterized Q&A
- **Objective:** Confirm student queries pull their personal record.
- **Manual Verification Steps:**
  1. On the home page (`http://127.0.0.1:5000/`), enter:
     `"What is my current placement status and technical rating?"`
  2. Click **Ask**.
  3. **Expected Result:** The system responds confirming student Aarav Patel's status and rating.

### Feature 3.3: Zero-Trust Guard: Cross-Student Aggregate Attack Blocking
- **Objective:** Ensure students cannot extract classmates' grades or batch statistics.
- **Manual Verification Steps:**
  1. As student `stu001`, submit the following query:
     `"Show me all students who have a CGPA greater than 8.0."`
  2. Click **Ask**.
  3. **Expected Result:** The query is blocked. The assistant immediately outputs:
     > *"Access Restricted: Institutional aggregates, batch statistics, and peer rankings are confidential and reserved for Placement Officers. You may ask questions about placement eligibility criteria, company visit schedules, or your personal placement profile."*

### Feature 3.4: Student Document Access Rules
- **Objective:** Ensure students can only see public documents.
- **Manual Verification Steps:**
  1. As student `stu001`, try accessing `http://127.0.0.1:5000/documents`.
  2. **Expected Result:** Blocked with an **Access Denied** flash message.
  3. Direct download attempt to internal file: `http://127.0.0.1:5000/documents/view/sample_internal_placement_strategy_memo.txt` -> Returns **HTTP 403 Forbidden**.

---

## 5. Module 4: Placement Coordinator Portal & Administration

### Feature 5.1: Non-Technical, User-Friendly Q&A Parameters
- **Objective:** Verify simplified controls for placement officers.
- **Manual Verification Steps:**
  1. Log in as `admin` / `admin123`.
  2. On the home page, inspect the left settings panel.
  3. **Expected Result:** Technical sliders (Temperature, Top-P, Top-K) are hidden. In their place are user-friendly presets:
     - **Response Style:** `Concise` | `Balanced` | `Detailed`
     - **Search Scope:** `Standard Search` | `Deep Search`
  4. Enter an institutional query:
     `"How many total students are in the placement tracker?"`
  5. **Expected Result:** Officer has administrative reach and receives batch numbers.

### Feature 5.2: Document Upload with Real-Time Progress Streaming
- **Objective:** Upload and index new documents into ChromaDB.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/documents`.
  2. Click **Upload Document**, select `test_resources/test_documents/sample_public_placement_circular_2026.txt`.
  3. Choose Visibility: **Public (Students & Staff)**.
  4. Click **Start Upload**.
  5. **Expected Result:** Real-time progress bar streams chunking, embedding, and vector insertion. A success banner confirms: *"Successfully indexed 1 new document(s) (public) into ChromaDB!"*

### Feature 5.3: Document Visibility Tagging (Public vs. Internal)
- **Objective:** Toggle document classification.
- **Manual Verification Steps:**
  1. Locate the uploaded document in the list.
  2. Click the visibility dropdown to change it from **Public** to **Internal (Staff Only)**.
  3. **Expected Result:** Audit event logs the visibility update, and the document is now masked from student view.

### Feature 5.4: Audit Logs Segregation
- **Objective:** Verify that developer actions are strictly hidden from officers.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/audit_logs`.
  2. Review the activity log table.
  3. **Expected Result:** Only actions by `admin` and `stu001` appear. No entries from `dev_admin` are visible.

### Feature 5.5: Student Account Management Segregation
- **Objective:** Verify officers cannot view or modify developer accounts.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/admin/users`.
  2. Inspect the user accounts table.
  3. **Expected Result:** Only student accounts (`stu001`) and the officer's own account (`admin`) appear. The `dev_admin` account does not appear in this list.

---

## 6. Module 5: Developer Portal, Impersonation & Safeguards

### Feature 6.1: Developer Telemetry Dashboard (`/dev/dashboard`)
- **Objective:** Monitor system health and vector store analytics.
- **Manual Verification Steps:**
  1. Log in as `dev_admin` / `DeveloperPass@1234`.
  2. Go to `http://127.0.0.1:5000/dev/dashboard`.
  3. **Expected Result:** Displays live ChromaDB total chunks, collection name, Ollama health status, and raw hardware telemetry.

### Feature 6.2: Technical Q&A Controls
- **Objective:** Unlocked engineering sliders for testing.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/` as `dev_admin`.
  2. **Expected Result:** Full parameter controls are exposed:
     - Temperature slider (`0.0` - `1.0`)
     - Top-P slider (`0.0` - `1.0`)
     - Top-K slider (`1` - `20`)
     - Raw System Prompt override textarea.

### Feature 6.3: Developer "View-As" (Impersonation) Mode
- **Objective:** Safely test the application from other personas.
- **Manual Verification Steps:**
  1. In the header bar, click **View As...** or go to `http://127.0.0.1:5000/dev/dashboard`.
  2. Select **Impersonate Student**, choose `STU001`, and click **Start View-As**.
  3. **Expected Result:**
     - A persistent amber banner appears at the top: *"VIEWING AS STUDENT (STU001) - Impersonation Active"*.
     - Navigation and views adapt to student mode.
  4. Test **Safe Permission Drop**: Attempt to navigate to `http://127.0.0.1:5000/dev/danger`.
     - **Expected Result:** Access is blocked with an Access Denied message.
  5. Click **Stop Impersonation** in the banner.
     - **Expected Result:** Returns to full Developer mode.

### Feature 6.4: Danger Zone Triple-Confirmation Safeguards (`/dev/danger`)
- **Objective:** Protect against accidental database wipes.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/dev/danger`.
  2. Try clicking **Wipe & Re-index** with an incorrect password -> **Blocked (403)**.
  3. Try with confirmation token `"reset"` (lowercase) -> **Blocked (400, must be uppercase 'RESET')**.
  4. Try with reason `"test"` (under 10 chars) -> **Blocked (400, reason must be >= 10 characters)**.

### Feature 6.5: Last Developer Immutability Protection
- **Objective:** Ensure the system cannot accidentally lock out all developers.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/dev/users`.
  2. Try demoting `dev_admin` to `student` or disabling the account.
  3. **Expected Result:** Blocked with constraint: *"Security constraint: The last active developer cannot be demoted / disabled."*

---

## 7. Module 6: Ticket-Based Issue Resolution Lifecycle

### Feature 7.1: Student Files Issue Ticket
- **Objective:** Verify student ticket submission.
- **Manual Verification Steps:**
  1. Log in as `stu001` / `Password@123`.
  2. Go to `http://127.0.0.1:5000/tickets` and click **+ New Issue Ticket**.
  3. Fill in:
     - **Title:** `Discrepancy in recorded CGPA`
     - **Category:** `Academic Record / CGPA`
     - **Priority:** `High`
     - **Description:** `My portal shows CGPA 8.10 but official transcript is 8.65.`
  4. Click **Submit Ticket**.
  5. **Expected Result:** Redirects to the ticket detail page. A ticket number (e.g. `TICK-2026-XXXX`) is assigned.

### Feature 7.2: Zero-Trust Ticket Privacy
- **Objective:** Ensure students cannot view other students' tickets.
- **Manual Verification Steps:**
  1. Note the ticket ID (e.g., `/tickets/1`).
  2. Create or log in as a different student account.
  3. Attempt to access `http://127.0.0.1:5000/tickets/1`.
  4. **Expected Result:** Blocked with: *"Access Denied: You do not have permission to view this ticket."*

### Feature 7.3: Coordinator Triage & Staff Internal Note vs Public Reply
- **Objective:** Coordinator communicates internally and publicly on a ticket.
- **Manual Verification Steps:**
  1. Log in as `admin` / `admin123`.
  2. Open the ticket (`http://127.0.0.1:5000/tickets/1`).
  3. Notice the **Student Record Snapshot drawer** on the right side, showing Aarav Patel's current record.
  4. In the reply box, type: `"Called exam branch coordinator to pull physical sheet."` Check the box **Post as Staff Internal Note**, then click **Send Reply**.
     - **Expected Result:** Appears with an amber **INTERNAL NOTE** tag.
  5. Post another reply without checking the internal box: `"We have received your request and will verify with the exam cell."`
     - **Expected Result:** Appears as a standard public message.
  6. Under Ticket Actions, update status to **In Progress**.

### Feature 7.4: Privacy Guard Verification (Student View)
- **Objective:** Verify the internal note is invisible to the student.
- **Manual Verification Steps:**
  1. Log back in as `stu001` / `Password@123`.
  2. Open the ticket (`http://127.0.0.1:5000/tickets/1`).
  3. **Expected Result:** The student sees the public message: *"We have received your request..."*. The internal note is **completely omitted** from the page.

### Feature 7.5: Coordinator Escalation to Developer & Resolution
- **Objective:** Cross-tier escalation for technical issues.
- **Manual Verification Steps:**
  1. Log in as `admin`. Go to `/tickets` -> **+ New Issue Ticket**.
  2. Select Target: **Developer / Technical Team**.
  3. Title: `ChromaDB vector embedding sync required`. Priority: `Urgent`.
  4. Log in as `dev_admin`, open the ticket, and set status to **Resolved** with resolution notes: `"Collection re-indexed successfully."`
  5. **Expected Result:** Ticket reflects **RESOLVED** status with a green resolution banner.

### Feature 7.6: Student Confirms Resolution & Closes Ticket
- **Objective:** Issue resolution lifecycle completion.
- **Manual Verification Steps:**
  1. Log in as `stu001`, open the resolved CGPA ticket.
  2. Click **Mark as Closed**.
  3. **Expected Result:** Ticket status transitions to **CLOSED**.

---

## 8. Module 7: Voice Typing & Dictation

### Feature 8.1: Windows Dictation Hotkey Trigger (Win+H)
- **Objective:** Hands-free voice query input.
- **Manual Verification Steps:**
  1. Go to `http://127.0.0.1:5000/`.
  2. Locate the microphone button in the Q&A input bar.
  3. Click the **Microphone** icon.
  4. **Expected Result:** A brief tooltip displays *"Triggered Windows Dictation (Win+H)"*, activating the native Windows Speech Recognition popup.

---

## 9. Module 8: Custom Error Handling Pages

### Feature 9.1: Custom 404 Not Found Page
- **Manual Verification Steps:**
  1. Navigate to: `http://127.0.0.1:5000/non_existent_page_url`.
  2. **Expected Result:** Custom dark glassmorphic 404 page with a **Return to Dashboard** button.

### Feature 9.2: Custom 403 Forbidden Page
- **Manual Verification Steps:**
  1. Log in as `stu001`.
  2. Navigate directly to `http://127.0.0.1:5000/documents/view/sample_internal_placement_strategy_memo.txt`.
  3. **Expected Result:** Custom dark glassmorphic 403 Forbidden page.

---

## 10. Automated Verification Suite

To run all checks across all 8 modules in a single step with colored terminal output:

```bash
python test_resources/verify_all_features.py
```

### Expected Output Summary:
```text
===========================================================================
 ALL 25 SYSTEM FEATURES VERIFIED & IN PERFECT WORKING CONDITION!
===========================================================================
```
