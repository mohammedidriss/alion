"""Dataset export — write and return the training manifest (ADR-013).

    POST /v2/datasets/{dataset_id}/export   → {dataset}/export/manifest.json

See `api.services.dataset_export` for what the manifest holds and how splits
are made.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.routes.auth import require_current_user
from api.routes.datasets import dataset_repo
from api.services import dataset_export
from store import DatasetRepo

router = APIRouter(
    prefix="/datasets", tags=["datasets"], dependencies=[Depends(require_current_user)]
)


@router.post("/{dataset_id}/export")
def export_dataset(dataset_id: UUID, repo: DatasetRepo = Depends(dataset_repo)) -> dict[str, Any]:
    dataset = repo.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    takes = [
        dataset_export.TakeRef(
            take_id=t.id,
            fighter_id=t.fighter_id,
            status=str(t.status),
            duration_ms=t.duration_ms or None,
        )
        for t in repo.takes(dataset_id)
    ]
    manifest = dataset_export.build_manifest(dataset_id, dataset.protocol, takes)
    path = dataset_export.write_manifest(dataset_id, manifest)
    return {**manifest, "path": str(path)}
