"""Tests for the School Hero portal page."""

from __future__ import annotations


def test_portal_route_returns_landing_html(demo_client):
    response = demo_client.get("/portal")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text

    assert "Школьный герой" in html
    assert "Сферум" in html
    assert "m.ospab.org" in html
    for heading in ("Ученик", "Педагог", "Директор", "Как подключить школу", "Контакты"):
        assert heading in html
    assert "vpn" not in html.lower()
    assert "<script" not in html.lower()


def test_landing_and_about_aliases(demo_client):
    for path in ("/landing", "/about"):
        res = demo_client.get(path)
        assert res.status_code == 200
        assert "Школьный герой" in res.text


def test_landing_static_assets_served(demo_client):
    css_res = demo_client.get("/landing/styles.css")
    assert css_res.status_code == 200
    assert "--accent" in css_res.text
    assert "gradient" not in css_res.text.lower()


def test_root_route_provides_portal_link(demo_client):
    res = demo_client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["portal"] == "/portal"
