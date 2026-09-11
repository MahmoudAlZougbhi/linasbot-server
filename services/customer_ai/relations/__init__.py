"""Relationship-aware helpers for Customer Brain."""

from __future__ import annotations

from services.customer_ai.relations.graph import load_relations, traverse

__all__ = ["load_relations", "traverse"]
