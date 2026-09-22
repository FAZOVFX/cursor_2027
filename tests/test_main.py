"""Tests for the entrypoint mode-selection logic (webhook vs polling)."""

from __future__ import annotations

from unittest.mock import MagicMock

from bot import main as main_module
from bot.config import load_config


def _patch_app(monkeypatch):
    app = MagicMock()
    monkeypatch.setattr(main_module, "build_application", lambda config: app)
    return app


def test_main_uses_webhook_on_render(monkeypatch):
    cfg = load_config(
        {"BOT_TOKEN": "123:abc", "RENDER_EXTERNAL_URL": "https://svc.onrender.com",
         "PORT": "10000"}
    )
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    app = _patch_app(monkeypatch)

    main_module.main()

    app.run_webhook.assert_called_once()
    _, kwargs = app.run_webhook.call_args
    assert kwargs["listen"] == "0.0.0.0"
    assert kwargs["port"] == 10000
    assert kwargs["url_path"] == "123:abc"
    assert kwargs["webhook_url"] == "https://svc.onrender.com/123:abc"
    app.run_polling.assert_not_called()


def test_main_uses_polling_without_webhook(monkeypatch):
    cfg = load_config({"BOT_TOKEN": "123:abc"})
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    app = _patch_app(monkeypatch)

    main_module.main()

    app.run_polling.assert_called_once()
    app.run_webhook.assert_not_called()
