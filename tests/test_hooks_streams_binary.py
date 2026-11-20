"""sys.stdout/stderr/stdin during in-process runs act like real ones (#300).

Binary writes through ``.buffer``, ``reconfigure()`` and binary reads from the
Experimental Console's stdin, as scripts do at a terminal.
"""

import io
import sys
from pathlib import Path

import pytest

from mypystub.hooks import ConsoleStdin, RunStream


def stream() -> tuple[RunStream, list[str], io.StringIO]:
    shown: list[str] = []
    log = io.StringIO()
    return RunStream(log, shown.append), shown, log


def test_buffer_writes_are_shown_and_logged() -> None:
    out, shown, log = stream()
    data = "café ✓\n".encode()
    out.buffer.write(data[:4])  # "caf" and the first byte of "é"
    out.buffer.write(data[4:])
    assert "".join(shown) == "café ✓\n" and log.getvalue() == "café ✓\n"


def test_undecodable_bytes_show_as_replacement() -> None:
    out, shown, _ = stream()
    out.buffer.write(b"\xff ok\n")
    assert "".join(shown) == "� ok\n"


def test_reconfigure_records_encoding_and_checks_it() -> None:
    out, shown, _ = stream()
    out.reconfigure(encoding="latin-1", line_buffering=True)
    assert out.encoding == "latin-1" and out.line_buffering and out.write_through
    out.buffer.write("é\n".encode("latin-1"))
    assert "".join(shown) == "é\n"
    with pytest.raises(LookupError):
        out.reconfigure(encoding="no-such-codec")
    with pytest.raises(ValueError):
        out.reconfigure(newline="x")


def test_console_stdin_buffer_reads_bytes() -> None:
    stdin = ConsoleStdin()
    stdin.feed("Sam\ncafé\n")
    stdin.feed_eof()
    assert stdin.buffer.readline() == b"Sam\n"
    assert stdin.buffer.read() == "café\n".encode()
    assert stdin.buffer.read() == b""


def test_console_stdin_buffer_partial_reads() -> None:
    stdin = ConsoleStdin()
    stdin.feed("abcdef\n")
    stdin.feed_eof()
    assert stdin.buffer.read(3) == b"abc"
    assert stdin.buffer.read1(10) == b"def\n"
    target = bytearray(4)
    assert stdin.buffer.readinto(target) == 0  # at EOF


def test_console_stdin_reconfigure() -> None:
    stdin = ConsoleStdin()
    stdin.reconfigure(encoding="latin-1")
    stdin.feed("café\n")
    assert stdin.buffer.readline() == "café\n".encode("latin-1")


# Through a real run, with the launcher's hooks in place

toga = pytest.importorskip("toga")
pytest.importorskip("toga_dummy")


def test_a_script_writing_bytes_shows_them(proto, app, docs: Path, monkeypatch) -> None:
    from tests.support_ui import run_to_end

    run_to_end(
        proto,
        app,
        docs,
        "import sys, shutil, io\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        "sys.stdout.buffer.write('bytes ✓\\n'.encode())\n"
        "shutil.copyfileobj(io.BytesIO(b'copied\\n'), sys.stdout.buffer)\n"
        "sys.stderr.buffer.write(b'to stderr\\n')\n",
        monkeypatch,
    )
    assert "bytes ✓\ncopied\n" in proto.print_text.value
    assert "to stderr" in proto.error_text.value


def test_the_launchers_own_streams_are_put_back(
    proto, app, docs: Path, monkeypatch
) -> None:
    from tests.support_ui import run_to_end

    before = sys.stdout
    run_to_end(proto, app, docs, "print('x')\n", monkeypatch)
    assert sys.stdout is before
