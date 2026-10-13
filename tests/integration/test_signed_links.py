"""Signed, expiring links for what can't send a login (ADR-017, part 2): the live
preview and heart-rate stream, profile photos, and the phones' join and studio
links."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi.testclient import TestClient

from api.services import signed


def test_a_signed_link_opens_only_what_it_was_made_for_until_it_expires() -> None:
    t = signed.sign("live", "abc", 60)
    assert signed.verify(t, "live", "abc")
    assert not signed.verify(t, "live", "abd")  # another resource
    assert not signed.verify(t, "photos", "abc")  # another purpose
    assert not signed.verify(t, "live", "abc", now=time.time() + 120)  # expired
    exp, mac = t.split(".", 1)
    assert not signed.verify(f"{int(exp, 16) + 3600:x}.{mac}", "live", "abc")  # stretched
    assert not signed.verify(None, "live", "abc") and not signed.verify("junk", "live", "abc")


def _session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Amir", "stance": "orthodox"}).json()["id"]
    return str(
        client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    )


def test_the_live_preview_and_heart_rate_stream_need_a_signed_link(
    authed_client: TestClient, client: TestClient
) -> None:
    sid = _session(authed_client)
    other = _session(authed_client)
    for path in (f"/sessions/{sid}/preview", f"/v2/sessions/{sid}/hrv/live"):
        assert client.get(path).status_code == 401  # no link
        assert client.get(f"{path}?t=junk").status_code == 401
    links = authed_client.get(f"/sessions/{sid}/live-links").json()
    assert "?t=" in links["preview"] and "?t=" in links["hrv_live"]
    # A link for one session doesn't open another.
    t = links["preview"].split("?t=")[1]
    assert client.get(f"/sessions/{other}/preview?t={t}").status_code == 401
    assert signed.verify(t, "live", sid)


def test_only_someone_who_may_see_the_session_gets_its_live_links(
    authed_client: TestClient, client: TestClient
) -> None:
    from api.services.terms import TERMS_VERSION

    sid = _session(authed_client)
    tok = client.post(
        "/auth/register",
        json={
            "email": "nosy@alion.test",
            "password": "ValidPass123",
            "name": "Nosy",
            "role": "fighter",
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    ).json()["access_token"]
    r = client.get(f"/sessions/{sid}/live-links", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_profile_photos_need_a_photo_pass(authed_client: TestClient, client: TestClient) -> None:
    path = f"/static/photos/fighter/{uuid4()}.jpg"
    assert client.get(path).status_code == 401
    assert client.get(f"{path}?t=junk").status_code == 401
    assert client.get("/auth/photo-pass").status_code == 401  # signed in only
    t = authed_client.get("/auth/photo-pass").json()["token"]
    assert client.get(f"{path}?t={t}").status_code == 404  # through the gate; no such photo


def test_a_join_link_expires_and_old_style_links_no_longer_work(
    authed_client: TestClient, client: TestClient
) -> None:
    sid = _session(authed_client)
    good = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    assert signed.expires(good) is not None
    ok = client.post(f"/sessions/{sid}/multicam/register", json={"token": good})
    assert ok.status_code == 200
    expired = signed.sign("multicam-join", sid, -1)
    old_style = "AbCdEfGhIjKlMnOp"  # the never-expiring kind
    for token in (expired, old_style):
        r = client.post(f"/sessions/{sid}/multicam/register", json={"token": token})
        assert r.status_code == 403


def test_unlinking_the_studio_ends_every_phones_link(
    authed_client: TestClient, client: TestClient
) -> None:
    old = authed_client.get("/v2/studio").json()["join_path"].split("studio=")[1]
    assert client.get(f"/studio/state?token={old}&phone_id=p1&label=Pixel").status_code == 200
    new = authed_client.post("/v2/studio/unlink").json()["join_path"].split("studio=")[1]
    assert new != old
    assert client.get(f"/studio/state?token={old}&phone_id=p1&label=Pixel").status_code == 403
    assert client.get(f"/studio/state?token={new}&phone_id=p1&label=Pixel").status_code == 200
