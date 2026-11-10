import socket

import pytest
from flaky_service import FlakyService


@pytest.fixture
def service():
    svc = FlakyService()
    svc.start()
    yield svc
    svc.stop()


def test_status_endpoint_replies_ok(service):
    # Depends on a service that sometimes drops the connection, with no retry.
    with socket.create_connection(("127.0.0.1", service.port), timeout=5) as conn:
        assert conn.recv(16) == b"ok"
