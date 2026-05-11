import httpx
import respx
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_invalid_path_returns_400():
    response = client.get("/proxy/archive.org")
    assert response.status_code == 400


def test_disallowed_host_returns_403():
    response = client.get("/proxy/evil.example.com/some/path")
    assert response.status_code == 403


def test_lookalike_host_returns_403():
    response = client.get("/proxy/fakearchive.org/some/path")
    assert response.status_code == 403


@respx.mock
def test_proxies_to_archive_org():
    respx.get("https://archive.org/details/example").mock(
        return_value=httpx.Response(
            200,
            content=b"hello",
            headers={"content-type": "text/plain", "content-length": "5"},
        )
    )
    response = client.get("/proxy/archive.org/details/example")
    assert response.status_code == 200
    assert response.content == b"hello"
    assert response.headers["content-type"] == "text/plain"


@respx.mock
def test_proxies_archive_org_subdomain():
    respx.get("https://ia800000.us.archive.org/path/to/file").mock(
        return_value=httpx.Response(200, content=b"data")
    )
    response = client.get("/proxy/ia800000.us.archive.org/path/to/file")
    assert response.status_code == 200
    assert response.content == b"data"


@respx.mock
def test_forwards_range_header_and_passes_through_range_response():
    url = "https://www.archive.org/download/OTMN103/03%20-%20Shoebill%20-%20mashup%20princess.mp3"
    route = respx.get(url).mock(
        return_value=httpx.Response(
            206,
            content=b"\x00" * 1024,
            headers={
                "content-type": "audio/mpeg",
                "content-length": "1024",
                "content-range": "bytes 0-1023/5000000",
                "accept-ranges": "bytes",
            },
        )
    )
    response = client.get(
        "/proxy/www.archive.org/download/OTMN103/03%20-%20Shoebill%20-%20mashup%20princess.mp3",
        headers={"Range": "bytes=0-1023"},
    )
    assert route.called
    assert route.calls.last.request.headers.get("Range") == "bytes=0-1023"
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-1023/5000000"
    assert response.headers["accept-ranges"] == "bytes"
    assert len(response.content) == 1024


@respx.mock
def test_does_not_forward_range_when_absent():
    route = respx.get("https://archive.org/details/example").mock(
        return_value=httpx.Response(200, content=b"ok")
    )
    client.get("/proxy/archive.org/details/example")
    assert route.called
    assert "Range" not in route.calls.last.request.headers
