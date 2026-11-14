from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.services import flood_evidence as svc
from app.services.audit import audit

router = APIRouter(prefix="/api/flood-evidence", tags=["flood-evidence"], dependencies=[Depends(require_staff)])


@router.get("")
def register(db: Session = Depends(get_db)) -> dict[str, Any]:
    return svc.register(db)


@router.post("/import")
async def import_csv(
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> dict[str, Any]:
    """Import an uploaded CSV, or the bundled November 2026 register when no file is sent. Re-importing updates by record_id."""
    if file is None:
        paths = svc.bundled_files()
        if not paths:
            raise HTTPException(status_code=404, detail="The bundled evidence files are missing.")
        source = ", ".join(p.name for p in paths)
        raws = [p.read_bytes() for p in paths]
    else:
        source = (file.filename or "upload.csv")[:120]
        raws = [await file.read(svc.MAX_BYTES + 1)]
    result: dict[str, Any] = {"added": 0, "updated": 0, "skipped_or_adjusted": 0, "problems": []}
    for raw in raws:
        if len(raw) > svc.MAX_BYTES:
            raise HTTPException(status_code=413, detail="The CSV is too large (limit 500 KB).")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="The CSV must be UTF-8 text.") from exc
        part = svc.import_text(db, text)
        for key in ("added", "updated", "skipped_or_adjusted"):
            result[key] += part[key]
        result["problems"] += part["problems"]
    result["problems"] = result["problems"][:50]
    if result["added"] == 0 and result["updated"] == 0:
        raise HTTPException(status_code=422, detail=" ".join(result["problems"][:3]) or "No usable rows.")
    audit(db, actor=actor, action="flood_evidence_import", entity_type="flood_evidence", entity_id=source[:64], detail={k: result[k] for k in ("added", "updated", "skipped_or_adjusted")})
    db.commit()
    return {"ok": True, "source": source, **result}
