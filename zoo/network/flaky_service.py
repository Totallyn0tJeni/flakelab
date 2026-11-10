"""A local TCP service that drops a quarter of its connections.

It stands in for an unreliable external API, so the zoo can contain a
network-dependent test without calling the real internet.
"""

import random
import socket
import threading

DROP_RATE = 0.25


class FlakyService:
    def __init__(self) -> None:
        self._server = socket.create_server(("127.0.0.1", 0))
        self.port: int = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.close()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return  # the server socket was closed
            with connection:
                if random.random() >= DROP_RATE:
                    connection.sendall(b"ok")
