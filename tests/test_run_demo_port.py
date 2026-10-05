"""Port guard for tools/run_demo.py: never start a second server on 8000."""
import socket

from tools.run_demo import port_in_use


def test_open_port_reports_free():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert port_in_use(free) is False


def test_listening_port_reports_in_use():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        assert port_in_use(s.getsockname()[1]) is True
