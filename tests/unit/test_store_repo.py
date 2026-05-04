"""FighterRepo unit tests — no API, no FastAPI."""

from __future__ import annotations

from sqlmodel import Session

from store import FighterRepo
from store.models import FighterCreate, Stance


def test_create_and_get(session: Session) -> None:
    repo = FighterRepo(session)
    fighter = repo.create(FighterCreate(name="Ali", stance=Stance.ORTHODOX))
    assert fighter.name == "Ali"
    fetched = repo.get(fighter.id)
    assert fetched is not None
    assert fetched.id == fighter.id


def test_list_and_delete(session: Session) -> None:
    repo = FighterRepo(session)
    repo.create(FighterCreate(name="A"))
    repo.create(FighterCreate(name="B"))
    assert len(repo.list_all()) == 2
    target = repo.list_all()[0]
    assert repo.delete(target.id) is True
    assert repo.delete(target.id) is False
    assert len(repo.list_all()) == 1
