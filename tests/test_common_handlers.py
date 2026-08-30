from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from workers import common_handlers as handlers


def _update(text="موضوع مقاله"):
    return SimpleNamespace(
        message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        effective_chat=SimpleNamespace(id=5544),
        effective_user=SimpleNamespace(first_name="کاربر"),
    )


def _article_context():
    return SimpleNamespace(
        user_data={
            "step": "article",
            "substep": 0,
            "steps": handlers.ARTICLE_STEPS,
            "data": {},
        }
    )


@pytest.mark.asyncio
async def test_article_submission_resets_conversation_after_queueing(monkeypatch):
    update = _update()
    context = _article_context()
    broker = MagicMock()
    broker.publish.return_value = b"1-0"
    show_menu = AsyncMock()

    async def connected(*_args):
        return {"site_url": "https://site.example", "secret": "secret"}

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
    monkeypatch.setattr(handlers, "require_connection", connected)
    monkeypatch.setattr(handlers, "get_platform", lambda _context: "telegram")
    monkeypatch.setattr(handlers, "article_broker", broker)
    monkeypatch.setattr(handlers, "show_main_menu", show_menu)

    await handlers.handle_message(update, context)

    broker.publish.assert_called_once()
    queued = broker.publish.call_args.args[0]
    assert queued["keywords"] == "موضوع مقاله"
    assert queued["platform"] == "telegram"
    assert queued["chat_id"] == "5544"
    assert "step" not in context.user_data
    show_menu.assert_awaited_once_with(update, context)
    assert any("مرحله پردازش" in call.args[0] for call in update.message.reply_text.await_args_list)

    # Regression guard: the next message must enter normal menu handling,
    # not index an exhausted steps list after a missing reset/early return.
    update.message.text = "چیز نامعتبر"
    await handlers.handle_message(update, context)
    assert any("1 یا 2 یا 3" in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_article_submission_explains_redis_failure_and_resets(monkeypatch):
    update = _update()
    context = _article_context()
    broker = MagicMock()
    broker.publish.side_effect = RuntimeError("Redis is unavailable: down")
    show_menu = AsyncMock()

    async def connected(*_args):
        return {"site_url": "https://site.example", "secret": "secret"}

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
    monkeypatch.setattr(handlers, "require_connection", connected)
    monkeypatch.setattr(handlers, "get_platform", lambda _context: "telegram")
    monkeypatch.setattr(handlers, "article_broker", broker)
    monkeypatch.setattr(handlers, "show_main_menu", show_menu)

    await handlers.handle_message(update, context)

    assert "step" not in context.user_data
    show_menu.assert_awaited_once_with(update, context)
    assert any("Redis" in call.args[0] for call in update.message.reply_text.await_args_list)


def test_product_flow_includes_grounding_steps_and_allows_notes_to_be_skipped():
    keys = [key for key, _question in handlers.PRODUCT_STEPS]
    assert keys[:3] == ["title", "product_type", "user_notes"]
    assert "user_notes" in handlers.SKIPPABLE_WITH_X
