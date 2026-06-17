import os

import aiohttp
import pytest
from aiohttp import web

from github_dlr.source import GITHUB_ACCESS_TOKEN_KEY, download_content, main


@pytest.mark.asyncio
async def test_download_content_succes(aiohttp_client, tmp_path):
    # aiohttp expects the url path to start with '/' hence not passing
    # the full Github URL here.
    download_url = "/AnimeChan/animechan/tree/main/client/public"
    mock_content = b"This is an image content"

    # Create test server to mock the download URL
    async def mock_handler(request):
        return web.Response(body=mock_content)

    app = web.Application()
    app.router.add_get(download_url, mock_handler)

    client = await aiohttp_client(app)
    download_url = client.make_url(download_url)

    # Use tmp_path fixure to create temp file path
    output_file = os.path.join(tmp_path, "foo.txt")

    # Download the file content and save it locally
    await download_content(download_url, output_file)

    # Verify the file was written correctly
    with open(output_file, "rb") as file:
        assert file.read() == mock_content


@pytest.mark.asyncio
async def test_download_content_failure(aiohttp_client, tmp_path):
    download_url = "/AnimeChan/animechan/tree/main/client/public"

    # Create test server to mock the download URL
    async def mock_handler(request):
        return web.Response(status=404)

    app = web.Application()
    app.router.add_get(download_url, mock_handler)

    client = await aiohttp_client(app)
    download_url = client.make_url(download_url)

    # Create a temp dir `tmp` to store the test files
    output_file = os.path.join(tmp_path, "foo.txt")

    with pytest.raises(aiohttp.ClientResponseError) as error:
        await download_content(download_url, output_file)

    assert error.value.status == 404


@pytest.mark.asyncio
async def test_download_content_uses_auth_header(
    aiohttp_client, tmp_path, monkeypatch
):
    download_url = "/private/file.txt"
    seen_auth = []

    async def mock_handler(request):
        seen_auth.append(request.headers.get("Authorization"))
        return web.Response(body=b"private")

    app = web.Application()
    app.router.add_get(download_url, mock_handler)

    client = await aiohttp_client(app)
    download_url = client.make_url(download_url)
    output_file = os.path.join(tmp_path, "foo.txt")

    monkeypatch.setenv(GITHUB_ACCESS_TOKEN_KEY, "token-123")
    await download_content(download_url, output_file)

    assert seen_auth == ["Bearer token-123"]


@pytest.mark.asyncio
async def test_main_reports_failed_downloads(
    aiohttp_client, tmp_path, capfd, monkeypatch
):
    async def mock_handler(request):
        return web.Response(status=500)

    app = web.Application()
    app.router.add_get("/bad.txt", mock_handler)
    client = await aiohttp_client(app)
    download_url = client.make_url("/bad.txt")

    async def mock_get_contents(content_url, *, ignore_extensions=None):
        return [{"name": "bad.txt", "download_url": download_url}]

    monkeypatch.setattr("github_dlr.source.get_contents", mock_get_contents)
    monkeypatch.setattr(
        "github_dlr.source.start_loading_animation", lambda message: None
    )
    monkeypatch.setattr(
        "github_dlr.source.stop_loading_animation", lambda thread: None
    )

    with pytest.raises(RuntimeError, match="1 file"):
        await main(
            "https://github.com/owner/repo/tree/main/public",
            output_dir=str(tmp_path),
        )

    captured_stdout = capfd.readouterr().out
    assert "1 file(s) failed" in captured_stdout
    assert "bad.txt" in captured_stdout
    assert str(download_url) in captured_stdout
    assert "Downloaded" not in captured_stdout
