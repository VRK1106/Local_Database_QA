# Comprehensive Walkthrough: Student Portal Enrichment, User Profile, System Settings & Custom Error Handling

This document provides a detailed overview of the student interface enhancements, profile system, user preferences, and branded error handling implemented in the Local Database Question-Answering System.

---

## 1. Student Portal Enrichment (Filling the Interface with Value)

To transform the previously sparse student interface into an interactive, high-value workspace without violating zero-trust data boundaries, the following components are integrated:

### A. Personalized Welcome & Academic Glance Banner
- Positioned above the query input in [templates/index.html](file:///d:/Non_Academic/Infosys_SpringBoard/Local_Database_QA/templates/index.html).
- Greets the student by username (`current_user.username`) and displays their verified Student USN (`current_user.student_id`) along with their enrolled academic department.
- Displays an automatic status badge indicating their standing:
  - **Placed Badge** (Emerald) if official records report a placed company.
  - **Verified CGPA Badge** (Cyan) with real-time academic standing.
  - **Zero-Trust Protected Badge** (Purple) if roster records are syncing.
- Direct link to [User Profile](file:///d:/Non_Academic/Infosys_SpringBoard/Local_Database_QA/templates/profile.html).

### B. Quick-Question Suggestion Chips
- Positioned directly above the `#query-input` textarea for instant one-click querying:
  - `🎯 Placement Eligibility`: Automatically fills and submits "Am I eligible for upcoming campus placement drives?".
  - `📄 PPO & Dream Policy`: Inquires about dream offer guidelines and pre-placement offer acceptance rules.
  - `📊 My Academic Standing`: Checks verified CGPA, credits, and active backlog records.
  - `🏛️ Tier-1 Criteria`: Summarizes cut-offs and criteria for Tier-1 recruitment drives.
- Placement Officer and Developer modes receive corresponding contextual quick chips (e.g., "Eligibility Criteria", "Recent Circulars", "Training Attendance").

### C. Student Placement Hub (Collapsible Right Column)
- Provides students with their own dedicated side panel rather than leaving the right side empty:
  - **Verified Academic Snapshot**: Shows verified CGPA, branch, active backlogs count, and drive eligibility.
  - **Official Public Circulars & Policies**: Lists all uploaded documents marked as `public`, complete with a direct `View` button linking to the document viewer.
  - **Recruitment Readiness Checklist**: 5 interactive checkboxes (ATS-friendly Resume, Portfolio / GitHub, Aptitude & Reasoning, Core CS & DSA, Mock HR Prep) with an animated progress bar and `localStorage` persistence.
  - **Speech Dispatcher Toggle**: Enables text-to-speech answer readout.
  - **Collapsible Toggle Button**: Allows students to collapse the side panel to enter distraction-free full-canvas mode whenever desired.

---

## 2. Dedicated User Profile (`/profile`)

Accessible from the sidebar and topbar username badge:
- **Student Profile**: Shows personal academic records parsed from official placement spreadsheets (`student_record`), student USN, enrolled branch, zero-trust privacy status, and password update links.
- **Placement Officer Profile**: Displays operational summary, student account counts, active indexed files, and audit trail metrics.
- **Developer Profile**: Highlights root privileges, direct links to Developer Control Center (`/dev`), Danger Zone (`/dev/danger`), and system diagnostics.

---

## 3. System Preferences & Settings (`/settings`)

Accessible from the topbar gear icon and navigation menu:
- **Speech Synthesis (TTS) Preferences**:
  - Voice selection menu dynamically populated with installed client-side Web Speech voices.
  - Speech playback rate slider ($0.7\times$ to $1.5\times$) with real-time audio testing.
  - Seamlessly applied to answer readouts across Q&A Studio.
- **Canvas Layout Preferences**:
  - Always start with side panel collapsed for maximum canvas width.
  - Toggle auto-scrolling to newly streamed AI answers.
- **Local Storage Cache Management**:
  - Clear student readiness checklists and local UI preferences in one click without affecting server databases.

---

## 4. Document Viewer with Scope Enforcement (`/documents/view/<filename>`)

- Public documents (`visibility = 'public'`) can be viewed/downloaded by all authenticated users.
- Internal documents (`visibility = 'internal'`) are strictly restricted to users with `docs.inspect` authority (Placement Officers and Developers).
- Unauthorized attempts to view internal documents trigger a `403 Forbidden` response displaying the custom branded security page.

---

## 5. Branded Error Handlers

Dark glassmorphic custom error pages adhering to the design system:
- **`403 Forbidden` (`templates/errors/403.html`)**: Details role boundaries and displays active security context (role, student ID).
- **`404 Not Found` (`templates/errors/404.html`)**: Clear missing resource notification with safe return links.
- **`500 Internal Server Error` (`templates/errors/500.html`)**: Graceful failure recovery page.
