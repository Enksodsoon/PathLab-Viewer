import builtins
import gc
import socket
import threading
import time
from pathlib import Path

import uvicorn
from test_desktop_sync import _client, _pair, _ready_slide
from wsi_viewer.database import session_factory
from wsi_viewer.models import Slide
from wsi_viewer.storage import StorageLayout


def test_desktop_content_early_disconnect_closes_source_without_gc(tmp_path, monkeypatch):
    with _client(tmp_path) as client:
        token = _pair(client)
        slide = _ready_slide(client)
        target = StorageLayout(client.app.state.settings.data_root).for_slide(slide.id).original
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            for _ in range(8):
                output.write(b"x" * 1024 * 1024)
        with session_factory(client.app.state.settings)() as database:
            database.get(Slide, slide.id).source_bytes = target.stat().st_size
            database.commit()

        sources = []
        original_open = builtins.open

        def observed_open(path, *args, **kwargs):
            source = original_open(path, *args, **kwargs)
            if isinstance(path, (str, Path)) and Path(path) == target and args and args[0] == "rb":
                sources.append(source)
            return source

        monkeypatch.setattr(builtins, "open", observed_open)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                client.app,
                log_level="error",
                lifespan="off",
                http="h11",
            )
        )
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        collection_enabled = gc.isenabled()
        connection = None
        gc.disable()
        try:
            thread.start()
            deadline = time.monotonic() + 3
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started, "Loopback server did not start"
            connection = socket.create_connection(("127.0.0.1", port), timeout=3)
            connection.settimeout(3)
            request = (
                f"GET /api/v2/desktop/slides/{slide.id}/content HTTP/1.1\r\n"
                f"Host: localhost\r\nAuthorization: Bearer {token['accessToken']}\r\n\r\n"
            )
            connection.sendall(request.encode())
            received = connection.recv(4096)
            assert b"HTTP/1.1 200" in received
            connection.close()
            connection = None
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if sources and all(source.closed for source in sources):
                    break
                time.sleep(0.02)
            assert sources, "Actual source descriptor was never opened"
            assert all(source.closed for source in sources), "Source retained after disconnect"
        finally:
            if connection is not None:
                connection.close()
            server.should_exit = True
            thread.join(3)
            if thread.is_alive():
                server.force_exit = True
                thread.join(1)
            listener.close()
            if collection_enabled:
                gc.enable()
        assert not thread.is_alive(), "Loopback server failed to shut down"
