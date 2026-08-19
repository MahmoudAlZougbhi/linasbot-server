"""CSV/XLSX import helpers for AI Products."""

from __future__ import annotations

import csv
import io
from typing import Any

from services.products.import_parser import normalize_header, normalize_import_row
from services.products.schemas import ProductWriteBody


class ProductsImportError(Exception):
    def __init__(self, *, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def preview_csv_rows(csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    headers = {normalize_header(h) for h in (reader.fieldnames or [])}
    if "name" not in headers:
        raise ProductsImportError(
            code="INVALID_CSV",
            message="csv_must_include_name_column",
            http_status=400,
        )
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    valid_count = 0
    for idx, raw in enumerate(reader, start=2):
        normalized = {normalize_header(str(k)): (v or "") for k, v in raw.items()}
        preview = normalize_import_row(normalized, row_number=idx)
        rows.append(preview)
        if preview.get("valid"):
            valid_count += 1
        else:
            errors.append({"row": str(idx), "error": str(preview.get("error") or "invalid_row")})
    return {
        "preview": rows,
        "valid_count": valid_count,
        "error_count": len(errors),
        "errors": errors,
        "import_format": "csv_v1",
    }


def import_csv_rows(svc: Any, *, tenant_id: str, csv_text: str) -> dict[str, Any]:
    preview = preview_csv_rows(csv_text)
    created = 0
    errors = list(preview.get("errors") or [])
    for row in preview.get("preview") or []:
        if not row.get("valid"):
            continue
        try:
            body = _body_from_preview(row)
            svc.create_product(tenant_id=tenant_id, body=body, require_description=False)
            created += 1
        except Exception as exc:
            code = getattr(exc, "code", None) or str(exc)
            errors.append({"row": str(row.get("row")), "error": str(code)})
    return {"created": created, "errors": errors, "import_format": "csv_v1"}


def preview_xlsx_rows(content: bytes) -> dict[str, Any]:
    from services.products.xlsx_import import parse_xlsx_bytes

    rows = parse_xlsx_bytes(content)
    if not rows:
        raise ProductsImportError(code="INVALID_XLSX", message="xlsx_empty_or_invalid", http_status=400)
    errors = [
        {"row": str(row.get("row")), "error": str(row.get("error") or "invalid_row")}
        for row in rows
        if not row.get("valid")
    ]
    valid_count = sum(1 for row in rows if row.get("valid"))
    return {
        "preview": rows,
        "valid_count": valid_count,
        "error_count": len(errors),
        "errors": errors,
        "import_format": "xlsx_v1",
    }


def import_xlsx_rows(svc: Any, *, tenant_id: str, content: bytes) -> dict[str, Any]:
    preview = preview_xlsx_rows(content)
    created = 0
    errors = list(preview.get("errors") or [])
    for row in preview.get("preview") or []:
        if not row.get("valid"):
            continue
        try:
            body = _body_from_preview(row)
            svc.create_product(tenant_id=tenant_id, body=body, require_description=False)
            created += 1
        except Exception as exc:
            code = getattr(exc, "code", None) or str(exc)
            errors.append({"row": str(row.get("row")), "error": str(code)})
    return {"created": created, "errors": errors, "import_format": "xlsx_v1"}


def _body_from_preview(row: dict[str, Any]) -> ProductWriteBody:
    return ProductWriteBody(
        name=str(row.get("name") or ""),
        description=(str(row.get("description") or "").strip() or None),
        price=row.get("price"),
        sizes=list(row.get("sizes") or []),
        colors=list(row.get("colors") or []),
        note=row.get("note"),
        availability=str(row.get("availability") or "in_stock"),
        images=[],
        links=list(row.get("links") or []),
    )
