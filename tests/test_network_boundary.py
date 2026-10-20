"""Only two modules may use the network: the dictionary download and the local web listener.

A person using a ROM-text tool should be able to trust that nothing phones home. This test
reads every source file's imports and fails if any other module imports a networking library.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "yomineko"
ALLOWED = SRC / "analyze" / "dictionary" / "source.py"
LISTENER = SRC / "web" / "server.py"  # binds 127.0.0.1 only; see test_web_security
NETWORK_MODULES = {
    "urllib",
    "http",
    "socket",
    "ssl",
    "ftplib",
    "smtplib",
    "xmlrpc",
    "requests",
    "httpx",
    "urllib3",
    "aiohttp",
    "uvicorn",
}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_download_module_imports_a_networking_library():
    offenders = {
        str(path.relative_to(SRC)): sorted(imported_roots(path) & NETWORK_MODULES)
        for path in SRC.rglob("*.py")
        if path not in (ALLOWED, LISTENER) and imported_roots(path) & NETWORK_MODULES
    }
    assert offenders == {}


def test_the_download_module_does_use_urllib():
    assert "urllib" in imported_roots(ALLOWED), "the allow-list entry should still be needed"


def test_the_listener_module_does_use_uvicorn_and_nothing_else_does():
    assert "uvicorn" in imported_roots(LISTENER), "the allow-list entry should still be needed"
    assert not imported_roots(LISTENER) & (NETWORK_MODULES - {"uvicorn"})
