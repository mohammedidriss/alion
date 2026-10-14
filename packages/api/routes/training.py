"""Train a dataset's camera punch counter on its export (services.training), and
the wrist sensors' punch-type model on every take (services.wrist_type_model).

POST /v2/datasets/{id}/train      start training on the latest export (202)
GET  /v2/datasets/{id}/training   running? which step, the latest report, every run
POST /v2/wrist-types/train        train and score the wrist punch-type model (ADR-029)
GET  /v2/wrist-types              its latest report
POST /v2/camera-types/train       train and score the cameras' punch-type model (ADR-034)
GET  /v2/camera-types             its latest report
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.access import Viewer, require_researcher
from api.routes.auth import require_current_user
from api.routes.datasets import dataset_repo
from api.services import camera_type_model, training, wrist_type_model
from store import DatasetRepo

router = APIRouter(prefix="/v2", tags=["training"], dependencies=[Depends(require_current_user)])


@router.post("/datasets/{dataset_id}/train", status_code=202, response_model=dict)
def train(dataset_id: UUID, repo: DatasetRepo = Depends(dataset_repo)) -> dict[str, Any]:
    """Train on the dataset's latest export — export first so it has every take."""
    if repo.get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not training.manifest_path(dataset_id).exists():
        raise HTTPException(status_code=409, detail="Export the dataset for training first")
    if not training.start(dataset_id):
        raise HTTPException(status_code=409, detail="Already training — wait for it to finish")
    return training.status(dataset_id)


@router.get("/datasets/{dataset_id}/training", response_model=dict)
def training_status(dataset_id: UUID, repo: DatasetRepo = Depends(dataset_repo)) -> dict[str, Any]:
    if repo.get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return training.status(dataset_id)


@router.get("/wrist-types", response_model=dict)
def wrist_types_report(_: Viewer = Depends(require_researcher)) -> dict[str, Any]:
    """The newest wrist punch-type model's report (None: never trained)."""
    return {"report": wrist_type_model.latest_report()}


@router.post("/wrist-types/train", response_model=dict)
def train_wrist_types(_: Viewer = Depends(require_researcher)) -> dict[str, Any]:
    """Train on every completed take's typed punches, score on takes held out, and
    save a new version — every session's punches are named again by it."""
    try:
        return {"report": wrist_type_model.train()}
    except wrist_type_model.BusyError as e:
        raise HTTPException(status_code=409, detail="Already training") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/camera-types", response_model=dict)
def camera_types_report(_: Viewer = Depends(require_researcher)) -> dict[str, Any]:
    """The newest camera punch-type model's report (None: never trained)."""
    return {"report": camera_type_model.latest_report()}


@router.post("/camera-types/train", response_model=dict)
def train_camera_types(_: Viewer = Depends(require_researcher)) -> dict[str, Any]:
    """Train on every completed take's typed punches as its cameras saw them, score
    on takes held out, and save a new version — every session is named again by it."""
    try:
        return {"report": camera_type_model.train()}
    except camera_type_model.BusyError as e:
        raise HTTPException(status_code=409, detail="Already training") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
