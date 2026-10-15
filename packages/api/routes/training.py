"""Train a dataset's camera punch counter on its export (services.training), and
the wrist sensors' punch-type model on every take (services.wrist_type_model).

POST /v2/datasets/{id}/train      start training on the latest export (202)
GET  /v2/punch-counter             the counter counting the cameras' punches (ADR-059)
GET  /v2/datasets/{id}/training   running? which step, the latest report, every run
POST /v2/wrist-types/train        train and score the wrist punch-type model (ADR-029)
GET  /v2/wrist-types              its latest report
POST /v2/camera-types/train       train and score the cameras' punch-type model (ADR-034)
GET  /v2/camera-types             its latest report
POST /v2/wrist-counter/train      train and score the wrists' punch counter (ADR-060)
GET  /v2/wrist-counter            its latest report
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.access import Viewer, require_researcher
from api.routes.auth import require_current_user
from api.routes.datasets import dataset_repo
from api.services import (
    camera_type_model,
    punch_counter,
    training,
    wrist_counter,
    wrist_type_model,
)
from store import DatasetRepo

router = APIRouter(prefix="/v2", tags=["training"], dependencies=[Depends(require_current_user)])


@router.post("/datasets/{dataset_id}/train", status_code=202, response_model=dict)
def train(
    dataset_id: UUID,
    include_others: bool = True,  # learn from the other exported datasets too (ADR-059)
    repo: DatasetRepo = Depends(dataset_repo),
) -> dict[str, Any]:
    """Train on the dataset's latest export — export first so it has every take —
    and, unless told not to, the other exported datasets' takes."""
    if repo.get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not training.manifest_path(dataset_id).exists():
        raise HTTPException(status_code=409, detail="Export the dataset for training first")
    if not training.start(dataset_id, include_others):
        raise HTTPException(status_code=409, detail="Already training — wait for it to finish")
    return training.status(dataset_id)


@router.get("/datasets/{dataset_id}/training", response_model=dict)
def training_status(dataset_id: UUID, repo: DatasetRepo = Depends(dataset_repo)) -> dict[str, Any]:
    if repo.get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    st = training.status(dataset_id)
    # The other datasets it learned from, by name (ADR-059).
    for o in ((st.get("latest") or {}).get("data") or {}).get("other_datasets") or []:
        ds = repo.get(UUID(o["dataset_id"]))
        o["name"] = ds.name if ds else None
    return st


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


@router.get("/wrist-counter", response_model=dict)
def wrist_counter_report(_: Viewer = Depends(require_researcher)) -> dict[str, Any]:
    """The newest wrist punch counter's report (None: never trained — the
    detector's defaults count)."""
    return {"report": wrist_counter.latest_report()}


@router.post("/wrist-counter/train", response_model=dict)
def train_wrist_counter(_: Viewer = Depends(require_researcher)) -> dict[str, Any]:
    """Train on every take's labelled protocol blocks, score on takes held out next
    to the detector's defaults, and save a new version — it counts every wrist
    punch from then on."""
    try:
        return {"report": wrist_counter.train()}
    except wrist_counter.BusyError as e:
        raise HTTPException(status_code=409, detail="Already training") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/punch-counter", response_model=dict)
def punch_counter_in_use(
    _: Viewer = Depends(require_researcher), repo: DatasetRepo = Depends(dataset_repo)
) -> dict[str, Any]:
    """Which counter counts the cameras' punches after a recording (ADR-059): the
    newest trained counter, or None — the hand-written detector."""
    cur = punch_counter.current()
    if cur is None:
        return {"counter": None}
    ds = repo.get(UUID(cur["dataset_id"])) if len(cur["dataset_id"]) == 36 else None
    test = cur["report"].get("test", {})
    return {
        "counter": {
            "dataset_id": cur["dataset_id"],
            "dataset_name": ds.name if ds else None,
            "version": cur["version"],
            "created_at": cur["report"].get("created_at"),
            "f1": test.get("model", {}).get("f1"),
            "precision": test.get("model", {}).get("precision"),
            "f1_detector": test.get("baseline", {}).get("f1"),
        }
    }
