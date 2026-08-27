import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture()
def tmp_db(tmp_path):
    """返回 (db_path, tmp_path)，供各测试建独立数据库。"""
    return tmp_path / "test.db", tmp_path
