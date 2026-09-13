"""pytest --geo flag: runs enterprise quality gates alongside unit tests."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--geo", action="store_true", default=False,
                     help="run enterprise GEO quality gates (eval/harvester/drift/API)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--geo"):
        return
    skip_geo = pytest.mark.skip(reason="needs --geo flag")
    for item in items:
        if "geo" in item.keywords:
            item.add_marker(skip_geo)
