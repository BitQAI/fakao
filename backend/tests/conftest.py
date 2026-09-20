import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app import ai


@pytest.fixture()
def tmp_db(tmp_path):
    """返回 (db_path, tmp_path)，供各测试建独立数据库。"""
    return tmp_path / "test.db", tmp_path


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """单测默认不联网：需要验证供应商链的用例自行 monkeypatch `provider_chain`。"""
    monkeypatch.setattr(ai, "provider_chain", list)
