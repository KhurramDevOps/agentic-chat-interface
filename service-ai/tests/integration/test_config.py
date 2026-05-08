"""
tests/integration/test_config.py  (T013)
──────────────────────────────────────────
Integration tests for startup config validation.

Validates that:
  - Settings loads correctly from environment.
  - The MongoDB rejection safeguard fires on forbidden variables.
  - Default values are sane.
  - The lru_cache singleton behaves correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestSettingsDefaults:
    def test_default_env_is_development(self):
        from app.core.config import Settings
        s = Settings()
        assert s.app_env == "development"

    def test_default_port_is_8000(self):
        from app.core.config import Settings
        s = Settings()
        assert s.app_port == 8000

    def test_default_log_level_is_info(self):
        from app.core.config import Settings
        s = Settings()
        assert s.log_level == "INFO"

    def test_default_litellm_model_set(self):
        from app.core.config import Settings
        s = Settings()
        assert s.litellm_model.startswith("gemini")

    def test_mem0_use_local_true_when_no_key(self):
        from app.core.config import Settings
        s = Settings(mem0_api_key="")
        assert s.mem0_use_local is True

    def test_mem0_use_local_false_when_key_set(self):
        from app.core.config import Settings
        s = Settings(mem0_api_key="some-key")
        assert s.mem0_use_local is False

    def test_is_production_false_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.is_production is False

    def test_is_production_true_when_set(self):
        from app.core.config import Settings
        s = Settings(app_env="production")
        assert s.is_production is True


class TestMongoDBSafeguard:
    """T011 — Constitution boundary: MongoDB variables must be rejected."""

    def test_rejects_mongodb_uri(self):
        from app.core.config import Settings
        with pytest.raises((ValidationError, ValueError)):
            Settings.model_validate({"mongodb_uri": "mongodb://localhost:27017"})

    def test_rejects_mongo_uri(self):
        from app.core.config import Settings
        with pytest.raises((ValidationError, ValueError)):
            Settings.model_validate({"mongo_uri": "mongodb://localhost:27017"})

    def test_rejects_mongodb_url(self):
        from app.core.config import Settings
        with pytest.raises((ValidationError, ValueError)):
            Settings.model_validate({"mongodb_url": "mongodb://localhost:27017"})

    def test_rejects_mongo_url(self):
        from app.core.config import Settings
        with pytest.raises((ValidationError, ValueError)):
            Settings.model_validate({"mongo_url": "mongodb://localhost:27017"})

    def test_accepts_non_mongo_config(self):
        from app.core.config import Settings
        # Should not raise
        s = Settings.model_validate({"app_env": "development", "app_port": 8000})
        assert s.app_port == 8000


class TestSettingsSingleton:
    def test_get_settings_returns_same_instance(self):
        from app.core.config import get_settings
        a = get_settings()
        b = get_settings()
        assert a is b

    def test_settings_instance_is_settings_type(self):
        from app.core.config import Settings, get_settings
        assert isinstance(get_settings(), Settings)


class TestPortValidation:
    def test_rejects_port_zero(self):
        from app.core.config import Settings
        with pytest.raises(ValidationError):
            Settings(app_port=0)

    def test_rejects_port_above_65535(self):
        from app.core.config import Settings
        with pytest.raises(ValidationError):
            Settings(app_port=65536)

    def test_accepts_valid_port(self):
        from app.core.config import Settings
        s = Settings(app_port=9000)
        assert s.app_port == 9000
