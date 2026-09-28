"""QueryScope Abstraction for Unified, Zero-Trust Data Isolation across Portals."""

from __future__ import annotations
from abc import ABC, abstractmethod
from flask import session


class QueryScope(ABC):
    """Abstract base class representing the bounded data reach of a query."""
    name: str

    @abstractmethod
    def chroma_where(self) -> dict | None:
        """Server-enforced metadata filter applied to every vector database query."""
        pass

    @abstractmethod
    def sql_mode(self) -> str:
        """Structured SQL mode: 'none' | 'own_record' | 'full'."""
        pass

    def bound_student_id(self) -> str | None:
        """The specific student ID to which SQL and record lookups are bound."""
        return None

    def can_access_document(self, doc_visibility: str) -> bool:
        """Check if this scope can read a document with the given visibility."""
        if self.chroma_where() and self.chroma_where().get("visibility") == "public":
            return str(doc_visibility).lower() == "public"
        return True


class StudentScope(QueryScope):
    """Student scope: strictly public vector chunks and session-bound personal SQL record."""
    name = "student"

    def __init__(self, student_id: str | None):
        self._student_id = student_id or ""

    def chroma_where(self) -> dict | None:
        return {"visibility": "public"}

    def sql_mode(self) -> str:
        return "own_record"

    def bound_student_id(self) -> str | None:
        return self._student_id


class PlacementScope(QueryScope):
    """Placement officer scope: public + internal documents and full universal SQL aggregates."""
    name = "placement"

    def chroma_where(self) -> dict | None:
        return None  # Unrestricted: accesses both public and internal documents

    def sql_mode(self) -> str:
        return "full"


class DeveloperScope(PlacementScope):
    """Developer scope: full system and data reach with administrative overrides."""
    name = "developer"


def scope_for(user) -> QueryScope:
    """
    Factory creating a QueryScope from the user's authenticated session.
    Honors developer impersonation ('view_as') by strictly dropping to the target scope.
    Never relies on user-supplied request payloads.
    """
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionError("Unauthenticated user cannot establish a QueryScope")

    # Developer Impersonation ('view_as')
    from flask import session, has_request_context
    if has_request_context():
        view_as = session.get("view_as")
        if user.role == "developer" and view_as:
            target_role = view_as.get("role")
            if target_role == "student":
                target_id = view_as.get("student_id") or "STU001"
                return StudentScope(target_id)
            if target_role == "placement":
                return PlacementScope()

    if user.role == "student":
        return StudentScope(user.student_id or user.username)
    if user.role == "placement":
        return PlacementScope()
    if user.role == "developer":
        return DeveloperScope()

    raise PermissionError(f"Unknown or unauthorized role: '{user.role}'")
