# Developer Role and Portal Abstraction Guide

**Project:** Placement QA System (Flask, Ollama, ChromaDB, SQLite router)
**Extends:** `RBAC_Implementation_Plan.md` (roles `placement` and `student`)
**Goal:** Add a `developer` role with all authorities, and separate the placement officer and student interfaces behind one shared core.

Confidence tags: **[Certain]** hard evidence, **[Likely]** strong inference, **[Guessing]** filling gaps.

---

## 1. Read This First

A developer role with "all authorities" is the largest insider risk in the whole system. It is a permanent backdoor to every student's CGPA, backlog count, and offer data. **[Certain]** Building it is reasonable. Building it as an ordinary account that logs in like everyone else is not.

**The design below makes the developer role all-powerful but constrained in how the power is used:**

- Created only from the server shell, never from the web UI.
- Every action logged with the real actor.
- Destructive actions need re-authentication plus a typed reason.
- A "view as" mode lets the developer test the student and placement portals without holding their permissions at the same time.

**Change to the earlier plan:** `/api/reset_db` moves from `placement` to `developer` only. A coordinator should not be able to wipe the database, even with password re-entry.

---

## 2. Role Hierarchy and Permissions

Use **explicit permission strings**, not just a rank number. A rank check (`role >= placement`) silently grants new permissions to higher roles when you add features. **[Likely]**

### Permission registry

| Permission | student | placement | developer |
| :--- | :---: | :---: | :---: |
| `query.public` (policy, criteria, notices) | ✅ | ✅ | ✅ |
| `query.own_record` | ✅ | ❌ | ✅ (own account, if linked) |
| `query.all` (full-table SQL, aggregates) | ❌ | ✅ | ✅ |
| `account.change_password` | ✅ | ✅ | ✅ |
| `docs.upload`, `docs.delete`, `docs.inspect`, `docs.tag` | ❌ | ✅ | ✅ |
| `users.import_students` | ❌ | ✅ | ✅ |
| `users.reset_student_password`, `users.disable_student` | ❌ | ✅ | ✅ |
| `audit.view_own_portal` (student and placement activity) | ❌ | ✅ | ✅ |
| `users.create_placement` | ❌ | ❌ | ✅ |
| `users.set_role` | ❌ | ❌ | ✅ |
| `system.config` (models, Top-K defaults, thresholds) | ❌ | ❌ | ✅ |
| `system.logs` (app logs, error traces) | ❌ | ❌ | ✅ |
| `audit.view_all` (includes developer actions) | ❌ | ❌ | ✅ |
| `db.reindex` | ❌ | ❌ | ✅ |
| `db.reset` (destructive, needs re-auth) | ❌ | ❌ | ✅ |
| `impersonate.student`, `impersonate.placement` | ❌ | ❌ | ✅ |

### Rules for role management

- Only a developer can create or change roles. A placement user cannot create another placement user or any developer.
- Developer accounts are created only through the CLI (section 5.1).
- The last active developer cannot be disabled or demoted. **[Likely]** This prevents locking yourself out.
- A developer cannot impersonate another developer.

---

## 3. Architecture: One Core, Three Interfaces

The interfaces differ only in **scope** (what data a query can reach) and **templates** (what the user sees). The retrieval, LLM, and trust-layer code stays shared and is never duplicated per role.

```
app/
├── __init__.py                 # app factory, blueprint registration
├── auth/
│   ├── models.py               # User model
│   ├── permissions.py          # PERMISSIONS map, has_permission()
│   ├── decorators.py           # permission_required()
│   └── routes.py               # /login, /logout, /change_password
├── core/
│   ├── scopes.py               # QueryScope base + Student/Placement/Developer
│   ├── query_engine.py         # answer_query(question, scope), shared by all portals
│   ├── ingestion.py            # tagging, chunking, visibility
│   └── audit.py                # audit writer
├── portals/
│   ├── student/
│   │   ├── routes.py           # blueprint: /student
│   │   └── templates/student/
│   ├── placement/
│   │   ├── routes.py           # blueprint: /placement
│   │   └── templates/placement/
│   └── developer/
│       ├── routes.py           # blueprint: /dev
│       └── templates/developer/
├── templates/base.html         # shared layout
└── cli.py                      # flask create-developer
```

### 3.1 The scope abstraction

Each portal builds a `QueryScope`. The query engine only ever sees the scope, never the raw role.

```python
# app/core/scopes.py
from abc import ABC, abstractmethod

class QueryScope(ABC):
    name: str

    @abstractmethod
    def chroma_where(self) -> dict | None:
        """Metadata filter applied to every vector query. Server-enforced."""

    @abstractmethod
    def sql_mode(self) -> str:
        """'none' | 'own_record' | 'full'"""

    def bound_student_id(self) -> str | None:
        return None


class StudentScope(QueryScope):
    name = "student"

    def __init__(self, student_id: str):
        self._student_id = student_id

    def chroma_where(self):
        return {"visibility": "public"}

    def sql_mode(self):
        return "own_record"

    def bound_student_id(self):
        return self._student_id


class PlacementScope(QueryScope):
    name = "placement"

    def chroma_where(self):
        return None            # public and internal documents

    def sql_mode(self):
        return "full"


class DeveloperScope(PlacementScope):
    name = "developer"         # same data reach as placement; extra powers live in /dev routes
```

### 3.2 Scope factory

```python
# app/core/scopes.py (continued)
from flask import session

def scope_for(user) -> QueryScope:
    view_as = session.get("view_as")           # set only by developer impersonation
    if user.role == "developer" and view_as:
        if view_as["role"] == "student":
            return StudentScope(view_as["student_id"])
        if view_as["role"] == "placement":
            return PlacementScope()
    if user.role == "student":
        return StudentScope(user.student_id)
    if user.role == "placement":
        return PlacementScope()
    if user.role == "developer":
        return DeveloperScope()
    raise PermissionError("Unknown role")
```

### 3.3 Shared query engine

```python
# app/core/query_engine.py
def answer_query(question: str, scope: QueryScope, top_k: int, model: str):
    where = scope.chroma_where()
    passages = vector_search(question, top_k=top_k, where=where)

    sql_result = None
    mode = scope.sql_mode()
    if mode == "full" and is_aggregate_query(question):
        sql_result = run_structured_query(question)                 # existing router
    elif mode == "own_record":
        sql_result = fetch_own_row(scope.bound_student_id())        # fixed, parameterized
    # mode == "none": no SQL at all

    return build_and_run_prompt(question, passages, sql_result, model)
```

Rules that must hold: **[Certain]**

- `scope` comes from `scope_for(current_user)`, never from the request body.
- On the student path, SQL is a fixed template bound to `student_id`. The LLM never writes SQL there.
- Adding a new portal means adding a new `QueryScope`, not editing the engine.

---

## 4. Permission Decorator and Portal Guards

```python
# app/auth/permissions.py
PERMISSIONS = {
    "student": {
        "query.public", "query.own_record", "account.change_password",
    },
    "placement": {
        "query.public", "query.all", "account.change_password",
        "docs.upload", "docs.delete", "docs.inspect", "docs.tag",
        "users.import_students", "users.reset_student_password",
        "users.disable_student", "audit.view_own_portal",
    },
}
PERMISSIONS["developer"] = PERMISSIONS["placement"] | {
    "query.own_record",
    "users.create_placement", "users.set_role",
    "system.config", "system.logs", "audit.view_all",
    "db.reindex", "db.reset",
    "impersonate.student", "impersonate.placement",
}

def has_permission(user, perm: str) -> bool:
    # While impersonating, the developer holds the target role's permissions only.
    from flask import session
    role = user.role
    view_as = session.get("view_as")
    if role == "developer" and view_as:
        role = view_as["role"]
    return perm in PERMISSIONS.get(role, set())
```

```python
# app/auth/decorators.py
from functools import wraps
from flask import abort
from flask_login import current_user

def permission_required(perm):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                abort(401)
            if not has_permission(current_user, perm):
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco
```

**Why permissions are dropped during impersonation:** if a developer viewing as a student still kept `db.reset`, one mis-click in the student view could wipe the database. Dropping to the target's permissions also makes the "view as" test faithful, because you see exactly what that role sees. **[Likely]**

### Portal-level guard (defense in depth)

Each blueprint refuses users whose role does not belong there, in addition to per-route checks.

```python
# app/portals/student/routes.py
student_bp = Blueprint("student", __name__, url_prefix="/student",
                       template_folder="templates")

@student_bp.before_request
def only_students_or_viewing_developer():
    if not current_user.is_authenticated:
        abort(401)
    effective = session.get("view_as", {}).get("role") if current_user.role == "developer" else current_user.role
    if effective != "student":
        abort(403)
```

Repeat for `placement_bp` (`effective == "placement"`, or a developer not impersonating) and `dev_bp` (`current_user.role == "developer"` and not impersonating).

### Post-login routing

```python
HOME = {"student": "student.home", "placement": "placement.home", "developer": "developer.home"}
# after successful login:
return redirect(url_for(HOME[user.role]))
```

---

## 5. Developer-Specific Instructions

### 5.1 Create the developer account (CLI only)

There is no web route for creating a developer. **[Certain]** A web route to create the most powerful account is a privilege-escalation path.

```python
# app/cli.py
import click
from getpass import getpass
from werkzeug.security import generate_password_hash

@click.command("create-developer")
@click.argument("username")
def create_developer(username):
    pw = getpass("Password: ")
    if pw != getpass("Confirm: "):
        raise click.ClickException("Passwords do not match")
    if len(pw) < 12:
        raise click.ClickException("Use at least 12 characters")
    db.execute(
        "INSERT INTO users (username, password_hash, role, active, must_change_password) "
        "VALUES (?, ?, 'developer', 1, 0)",
        (username, generate_password_hash(pw)),
    )
    db.commit()
    click.echo(f"Developer '{username}' created")
```

Register it in the app factory: `app.cli.add_command(create_developer)`. Run with `flask create-developer <username>`.

**[Likely]** Keep developer accounts to one or two. Each extra one is another credential that can leak.

### 5.2 Hardening for developer sessions

| Control | Setting |
| :--- | :--- |
| Session lifetime | Shorter than other roles, for example 15 minutes idle |
| Second factor | TOTP via `pyotp`, required at login for `role == "developer"` **[Likely]** worth it |
| Network restriction | Optional allowlist so `/dev/*` accepts only localhost or an admin subnet |
| Cookie flags | `HttpOnly`, `SameSite=Lax`, `Secure` once HTTPS is on |
| Password hashing | `generate_password_hash`, never plaintext |

### 5.3 Destructive actions: re-auth, reason, typed confirmation

Applies to `db.reset`, `db.reindex`, and role changes.

```python
@dev_bp.post("/reset_db")
@permission_required("db.reset")
def reset_db():
    data = request.get_json()
    if not check_password_hash(current_user.password_hash, data.get("password", "")):
        abort(403)
    if data.get("confirm") != "RESET":
        abort(400)
    reason = (data.get("reason") or "").strip()
    if len(reason) < 10:
        abort(400, "A reason is required")
    audit.write(actor=current_user.id, effective_role="developer",
                action="db.reset", detail=reason)
    do_reset()
    return {"ok": True}
```

### 5.4 Impersonation ("view as")

```python
@dev_bp.post("/view_as")
@permission_required("impersonate.student")
def view_as():
    data = request.get_json()
    if data["role"] == "student":
        target = get_student_user(data["student_id"])
        session["view_as"] = {"role": "student", "student_id": target.student_id}
    elif data["role"] == "placement":
        session["view_as"] = {"role": "placement"}
    else:
        abort(400)
    audit.write(actor=current_user.id, effective_role=data["role"],
                action="impersonate.start", detail=str(data))
    return redirect(url_for(HOME[data["role"]]))

@dev_bp.post("/view_as/stop")
def stop_view_as():
    session.pop("view_as", None)
    audit.write(actor=current_user.id, effective_role="developer", action="impersonate.stop")
    return redirect(url_for("developer.home"))
```

Rules:

- Show a persistent banner in every template while `session["view_as"]` is set, for example "Viewing as student STU004. Exit."
- Reject impersonating any user whose role is `developer`.
- The `/view_as/stop` route must stay reachable while impersonating, so it uses a plain `login_required` check rather than `permission_required("impersonate.*")`, which drops to the target role's permissions.

### 5.5 Developer portal pages

| Page | Purpose |
| :--- | :--- |
| `/dev/users` | List, create placement users, change roles, disable accounts |
| `/dev/config` | Ollama model, default Top-K, trust-layer thresholds |
| `/dev/logs` | Application logs and error traces |
| `/dev/audit` | Full audit log including developer actions, filterable by actor and action |
| `/dev/index` | Reindex, visibility tag report, orphaned-chunk report |
| `/dev/view_as` | Pick a student or the placement role to preview |
| `/dev/danger` | Reset DB, behind the re-auth form in 5.3 |

Developers also keep access to the placement pages (upload, delete, inspect) through the shared permission set, so they can be reached from the developer home without switching accounts.

---

## 6. Audit Log Changes

The audit table needs to record the real actor and the effective role separately. **[Certain]** Otherwise impersonated actions look like they came from the student.

| Column | Meaning |
| :--- | :--- |
| `actor_user_id` | The logged-in user, always the real one |
| `effective_role` | The role the action ran under (differs from actor's role during impersonation) |
| `effective_student_id` | Set when impersonating a student |
| `action` | e.g. `query`, `docs.upload`, `db.reset`, `impersonate.start` |
| `detail` | Query text, filename, or reason |
| `sources` | Retrieved document names |
| `timestamp` | UTC |

Developer queries with `query.all` are logged like any other. Developers should not be exempt from logging.

---

## 7. Implementation Order

1. Complete the base RBAC plan first: `users` table, login, `visibility` tags, student scoped path, audit log.
2. Add `developer` to the role column, then the `PERMISSIONS` map and `permission_required`. Replace existing `role_required` calls.
3. Introduce `QueryScope` classes and route `/api/query` through `scope_for`.
4. Split templates and routes into the three blueprints with portal guards.
5. Add the `create-developer` CLI and create your account.
6. Move `db.reset` and `db.reindex` to the developer portal with re-auth and reason.
7. Add impersonation with the banner and the audit fields.
8. Add developer session hardening: shorter lifetime, then TOTP.

---

## 8. Risks

| Risk | Detail |
| :--- | :--- |
| **Developer as a standing backdoor** | Full data reach with no friction becomes the easiest account to abuse or steal. Logging, TOTP, and a short session are the mitigations. They reduce the risk and do not remove it. **[Certain]** |
| **Rank-based checks creeping back** | If someone later writes `if user.role != "student"`, developer and placement get access by accident. Use `has_permission` everywhere. **[Likely]** |
| **Impersonation state leaking** | `session["view_as"]` left set after logout would carry into the next login on a shared browser. Clear the session fully on logout. **[Likely]** |
| **Stale permission map** | Adding a feature without registering its permission string means it is silently unreachable or, worse, unguarded. Fail closed: an unknown permission returns `False`. |
| **Blueprint templates colliding** | Two template folders with the same filename resolve to the first match. Namespace templates under `student/`, `placement/`, `developer/` as shown in section 3. |
| **Developer account and the identity key** | If a developer is also linked to a `student_id` for testing, that link must not let them read other students under the student path. The student path stays bound to the single ID. |

---

## 9. Definition of Done

- [ ] A student session gets 403 on every `/placement/*` and `/dev/*` route.
- [ ] A placement session gets 403 on every `/dev/*` route and on `db.reset`.
- [ ] No web route creates a developer account; only the CLI does.
- [ ] While viewing as a student, `db.reset` returns 403 for the developer.
- [ ] While viewing as a student, queries cannot reach `internal` chunks or other students' rows.
- [ ] Every audit row for an impersonated action shows the real `actor_user_id`.
- [ ] `db.reset` fails without password, the typed `RESET`, and a reason.
- [ ] The last active developer cannot be disabled or demoted.
- [ ] Logout clears `view_as` and the whole session.
- [ ] Unknown permission strings resolve to denied.
