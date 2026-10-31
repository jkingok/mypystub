"""Tests for export_ssl_cert_bundle() in mypystub.app."""

import os
import sys

import certifi
import pytest

from mypystub.app import export_ssl_cert_bundle


def test_sets_ssl_cert_file_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With SSL_CERT_FILE unset, it is pointed at certifi's bundle."""
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    export_ssl_cert_bundle()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()


def test_keeps_existing_ssl_cert_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """An SSL_CERT_FILE set by the user or platform is left alone."""
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
    export_ssl_cert_bundle()
    assert os.environ["SSL_CERT_FILE"] == "/custom/ca.pem"


def test_missing_certifi_logs_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If certifi cannot be imported, a message is printed and nothing is set."""
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    # A None entry in sys.modules makes `import certifi` raise ImportError.
    monkeypatch.setitem(sys.modules, "certifi", None)
    export_ssl_cert_bundle()
    assert "SSL_CERT_FILE" not in os.environ
    assert "certifi unavailable" in capsys.readouterr().out
