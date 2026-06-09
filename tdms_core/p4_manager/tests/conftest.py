# tdms_core/p4_manager/tests/conftest.py
import pytest

def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False)

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="--run-integration 플래그 없이는 실행 안 됨")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
