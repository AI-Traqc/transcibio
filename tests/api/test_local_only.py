import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.api.local_only import LocalOnlyMiddleware
from backend.app.config import DEFAULT_ALLOWED_HOSTS, parse_allowed_hosts


def _client() -> TestClient:
    app = FastAPI()

    @app.post("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.websocket("/ws")
    async def echo(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_text(await ws.receive_text())
        await ws.close()

    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=DEFAULT_ALLOWED_HOSTS)
    return TestClient(app, base_url="http://localhost:8000")


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8080", "LOCALHOST", "[::1]:8000"])
def test_local_same_origin_request_passes(host):
    response = _client().post("/ping", headers={"Host": host, "Origin": "http://localhost:5173"})

    assert response.status_code == 200


def test_request_without_origin_passes():
    # curl, scripts and the launcher's health check send no Origin header.
    assert _client().post("/ping").status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "[::1"])
def test_foreign_or_malformed_host_is_rejected(host):
    # DNS rebinding: evil.example re-pointed at 127.0.0.1 still sends its own Host header.
    response = _client().post("/ping", headers={"Host": host})

    assert response.status_code == 400


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost.evil.example", "null"])
def test_cross_origin_request_is_rejected(origin):
    response = _client().post("/ping", headers={"Origin": origin})

    assert response.status_code == 403


def test_cross_origin_websocket_is_rejected_before_accept():
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with _client().websocket_connect(
            "ws://localhost:8000/ws", headers={"Origin": "http://evil.example"}
        ):
            pass

    assert exc_info.value.code == 1008


def test_same_origin_websocket_passes():
    with _client().websocket_connect(
        "ws://localhost:8000/ws", headers={"Origin": "http://localhost:8080"}
    ) as ws:
        ws.send_text("hallo")
        assert ws.receive_text() == "hallo"


def test_parse_allowed_hosts_keeps_localhost_and_adds_extras():
    assert parse_allowed_hosts(None) == DEFAULT_ALLOWED_HOSTS
    assert parse_allowed_hosts(" Spark.local , [fe80::1],localhost,, ") == (
        *DEFAULT_ALLOWED_HOSTS,
        "spark.local",
        "fe80::1",
    )
