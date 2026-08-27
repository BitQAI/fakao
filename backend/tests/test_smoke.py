from app import config


def test_config_paths():
    assert config.BACKEND_DIR.name == "backend"
    assert config.ROOT_DIR.name == "fk"
    assert config.DB_PATH.name == "fakao.db"
    assert config.CASES_INDEX.name == "index.csv"


def test_env_placeholder_example_exists():
    assert (config.ROOT_DIR / ".env.example").exists()
