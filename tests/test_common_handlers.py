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


async def _drive_article_flow(handlers_module, update, context, *, keywords="موضوع مقاله", article_type="راهنمای خرید", notes="x", image_reply="-"):
    """Feed all ARTICLE_STEPS answers through handle_message in order,
    then the featured-image step (skipped by default), mirroring how a
    real conversation completes the chain."""

    for text in (keywords, article_type, notes, image_reply):
        update.message.text = text
        await handlers_module.handle_message(update, context)


@pytest.mark.asyncio
async def test_article_submission_persists_before_queueing_only_durable_job_id(monkeypatch):
    update = _update()
    context = _article_context()
    broker = MagicMock()
    show_menu = AsyncMock()
    calls = []

    def publish(payload):
        calls.append(("publish", payload))
        return "1710000000000-0"

    broker.publish.side_effect = publish

    async def connected(*_args):
        return {"site_url": "https://site.example", "secret": "secret"}

    def create_job(tenant_id, **kwargs):
        calls.append(("create", tenant_id, kwargs))
        return 81

    def mark_queued(job_id, stream_id):
        calls.append(("queued", job_id, stream_id))
        return True

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
    monkeypatch.setattr(handlers, "require_connection", connected)
    monkeypatch.setattr(handlers, "create_article_job", create_job)
    monkeypatch.setattr(handlers, "mark_article_job_queued", mark_queued)
    monkeypatch.setattr(handlers, "article_broker", broker)
    monkeypatch.setattr(handlers, "show_main_menu", show_menu)

    await _drive_article_flow(handlers, update, context)

    assert calls[0] == ("create", 1, {
        "keywords": "موضوع مقاله",
        "article_type": "راهنمای خرید",
        "notes": "",  # "x" means skipped
        "featured_image_url": None,  # "-" means the image step was skipped
        "chapters": 5,
        "max_words": 500,
        "tone": "informative",
        "audience": "general",
        "source": "bot",
    })
    broker.publish.assert_called_once_with({"job_id": "81"})
    assert calls[1] == ("publish", {"job_id": "81"})
    assert calls[2] == ("queued", 81, "1710000000000-0")
    assert "step" not in context.user_data
    show_menu.assert_awaited_once_with(update, context)
    assert any("مرحله پردازش" in call.args[0] for call in update.message.reply_text.await_args_list)
    assert any("81" in call.args[0] for call in update.message.reply_text.await_args_list)

    # Regression guard: the next message must enter normal menu handling,
    # not index an exhausted steps list after a missing reset/early return.
    update.message.text = "چیز نامعتبر"
    await handlers.handle_message(update, context)
    assert any("1 یا 2 یا 3" in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_article_submission_records_redis_failure_after_durable_creation(monkeypatch):
    update = _update()
    context = _article_context()
    broker = MagicMock()
    broker.publish.side_effect = RuntimeError("Redis is unavailable: down")
    show_menu = AsyncMock()
    failed = MagicMock(return_value=True)

    async def connected(*_args):
        return {"site_url": "https://site.example", "secret": "secret"}

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
    monkeypatch.setattr(handlers, "require_connection", connected)
    monkeypatch.setattr(handlers, "create_article_job", lambda *_args, **_kwargs: 82)
    monkeypatch.setattr(handlers, "mark_article_job_failed", failed)
    monkeypatch.setattr(handlers, "article_broker", broker)
    monkeypatch.setattr(handlers, "show_main_menu", show_menu)

    await _drive_article_flow(handlers, update, context)

    broker.publish.assert_called_once_with({"job_id": "82"})
    failed.assert_called_once()
    assert failed.call_args.args[0] == 82
    assert "Redis queue publish failed" in failed.call_args.args[1]
    assert "step" not in context.user_data
    show_menu.assert_awaited_once_with(update, context)
    assert any("Redis" in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_article_submission_does_not_publish_when_database_creation_fails(monkeypatch):
    update = _update()
    context = _article_context()
    broker = MagicMock()
    show_menu = AsyncMock()

    async def connected(*_args):
        return {"site_url": "https://site.example", "secret": "secret"}

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
    monkeypatch.setattr(handlers, "require_connection", connected)
    monkeypatch.setattr(handlers, "create_article_job", MagicMock(side_effect=RuntimeError("database down")))
    monkeypatch.setattr(handlers, "article_broker", broker)
    monkeypatch.setattr(handlers, "show_main_menu", show_menu)

    await _drive_article_flow(handlers, update, context)

    broker.publish.assert_not_called()
    assert "step" not in context.user_data
    assert any("دیتابیس" in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_start_consumes_only_the_matching_platform_pairing_token(monkeypatch):
    token = "C" * 43
    update = _update()
    context = SimpleNamespace(
        user_data={},
        args=["connect_" + token],
        application=SimpleNamespace(bot_data={"platform": "telegram"}),
    )
    consume = MagicMock(return_value={"site_url": "https://shop.example", "secret": "never-display"})
    verify = AsyncMock(return_value=True)

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 71)
    monkeypatch.setattr(handlers, "consume_pending_connection", consume)
    monkeypatch.setattr(handlers, "_verify_and_save_site", verify)

    await handlers.start(update, context)

    consume.assert_called_once_with(token, "telegram")
    verify.assert_awaited_once_with(
        update,
        context,
        71,
        "https://shop.example",
        "never-display",
        strict_one_click=True,
    )
    # The one-time secret is never sent in a chat reply before verification.
    assert all("never-display" not in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_start_rejects_malformed_or_wrong_platform_pairing_without_save(monkeypatch):
    update = _update()
    malformed_context = SimpleNamespace(
        user_data={},
        args=["connect_too-short"],
        application=SimpleNamespace(bot_data={"platform": "telegram"}),
    )
    consume = MagicMock()
    verify = AsyncMock()
    menu = AsyncMock()

    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 72)
    monkeypatch.setattr(handlers, "consume_pending_connection", consume)
    monkeypatch.setattr(handlers, "_verify_and_save_site", verify)
    monkeypatch.setattr(handlers, "show_main_menu", menu)

    await handlers.start(update, malformed_context)
    consume.assert_not_called()
    verify.assert_not_awaited()

    token = "D" * 43
    wrong_platform_context = SimpleNamespace(
        user_data={},
        args=["connect_" + token],
        application=SimpleNamespace(bot_data={"platform": "bale"}),
    )
    consume.return_value = None  # repository reports an intended Telegram token as unavailable to Bale

    await handlers.start(update, wrong_platform_context)

    consume.assert_called_once_with(token, "bale")
    verify.assert_not_awaited()
    assert any("ربات دیگری" in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_failed_site_verification_never_overwrites_a_tenant_connection(monkeypatch):
    update = _update()
    context = SimpleNamespace(user_data={})
    saved = MagicMock()
    menu = AsyncMock()

    class RejectingSite:
        def __init__(self, *_args, **_kwargs):
            pass

        def ping(self):
            raise handlers.SiteConnectorError("invalid secret")

    monkeypatch.setattr(handlers, "assert_site_host_is_public", lambda _url: None)
    monkeypatch.setattr(handlers, "SiteConnectorClient", RejectingSite)
    monkeypatch.setattr(handlers, "save_wp_connection", saved)
    monkeypatch.setattr(handlers, "show_main_menu", menu)

    assert await handlers._verify_and_save_site(
        update,
        context,
        73,
        "https://shop.example",
        "bad",
        strict_one_click=True,
    ) is False
    saved.assert_not_called()


@pytest.mark.asyncio
async def test_one_click_requires_a_successful_matching_ping_before_save(monkeypatch):
    update = _update()
    context = SimpleNamespace(user_data={})
    saved = MagicMock()

    class UnconfirmedSite:
        def __init__(self, *_args, **_kwargs):
            pass

        def ping(self):
            return {"success": False, "site_url": "https://shop.example"}

    monkeypatch.setattr(handlers, "assert_site_host_is_public", lambda _url: None)
    monkeypatch.setattr(handlers, "SiteConnectorClient", UnconfirmedSite)
    monkeypatch.setattr(handlers, "save_wp_connection", saved)
    monkeypatch.setattr(handlers, "show_main_menu", AsyncMock())

    assert await handlers._verify_and_save_site(
        update,
        context,
        74,
        "https://shop.example",
        "secret",
        strict_one_click=True,
    ) is False
    saved.assert_not_called()


def test_product_flow_includes_grounding_steps_and_allows_notes_to_be_skipped():
    keys = [key for key, _question in handlers.PRODUCT_STEPS]
    assert keys[:3] == ["title", "product_type", "user_notes"]
    assert "user_notes" in handlers.SKIPPABLE_WITH_X


def test_article_flow_includes_grounding_steps_and_allows_notes_to_be_skipped():
    keys = [key for key, _question in handlers.ARTICLE_STEPS]
    assert keys == ["keywords", "article_type", "notes"]
    assert "notes" in handlers.SKIPPABLE_WITH_X


@pytest.mark.asyncio
async def test_article_image_step_accepts_various_skip_tokens(monkeypatch):
    for skip_word in ("-", "x", "X", "رد", "skip"):
        update = _update()
        context = _article_context()

        async def connected(*_args):
            return {"site_url": "https://site.example", "secret": "secret"}

        create_job = MagicMock(return_value=90)
        monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
        monkeypatch.setattr(handlers, "require_connection", connected)
        monkeypatch.setattr(handlers, "create_article_job", create_job)
        monkeypatch.setattr(handlers, "mark_article_job_queued", lambda *_a: True)
        monkeypatch.setattr(handlers, "article_broker", MagicMock(publish=MagicMock(return_value="1-0")))
        monkeypatch.setattr(handlers, "show_main_menu", AsyncMock())

        await _drive_article_flow(handlers, update, context, image_reply=skip_word)

        assert create_job.call_args.kwargs["featured_image_url"] is None, skip_word


@pytest.mark.asyncio
async def test_article_image_step_rejects_non_skip_text_and_waits_for_a_photo(monkeypatch):
    update = _update()
    context = _article_context()
    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)

    for text in ("موضوع مقاله", "راهنمای خرید", "x"):
        update.message.text = text
        await handlers.handle_message(update, context)

    update.message.text = "یه متن نامربوط"
    await handlers.handle_message(update, context)

    assert context.user_data["step"] == "awaiting_article_image"
    assert any("یه عکس بفرست" in call.args[0] for call in update.message.reply_text.await_args_list)


@pytest.mark.asyncio
async def test_article_featured_image_upload_finalizes_the_job(monkeypatch):
    update = _update()
    context = _article_context()

    async def connected(*_args):
        return {"site_url": "https://site.example", "secret": "secret"}

    create_job = MagicMock(return_value=91)
    monkeypatch.setattr(handlers, "get_tenant_id", lambda *_args: 1)
    monkeypatch.setattr(handlers, "require_connection", connected)
    monkeypatch.setattr(handlers, "create_article_job", create_job)
    monkeypatch.setattr(handlers, "mark_article_job_queued", lambda *_a: True)
    monkeypatch.setattr(handlers, "article_broker", MagicMock(publish=MagicMock(return_value="1-0")))
    monkeypatch.setattr(handlers, "show_main_menu", AsyncMock())

    for text in ("موضوع مقاله", "راهنمای خرید", "x"):
        update.message.text = text
        await handlers.handle_message(update, context)
    assert context.user_data["step"] == "awaiting_article_image"

    fake_file = AsyncMock()
    fake_file.download_to_drive = AsyncMock()
    photo_update = SimpleNamespace(
        message=SimpleNamespace(
            text=None,
            reply_text=AsyncMock(),
            photo=[SimpleNamespace(get_file=AsyncMock(return_value=fake_file))],
            document=None,
        ),
        effective_chat=SimpleNamespace(id=5544),
        effective_user=SimpleNamespace(first_name="کاربر"),
    )

    class FakeSite:
        def __init__(self, *_a):
            pass

        def upload_media(self, file_path):
            return {"success": True, "url": "https://site.example/wp-content/uploads/img.jpg"}

    monkeypatch.setattr(handlers, "SiteConnectorClient", FakeSite)
    monkeypatch.setattr("os.remove", lambda *_a: None)

    await handlers.handle_file(photo_update, context)

    assert create_job.call_args.kwargs["featured_image_url"] == "https://site.example/wp-content/uploads/img.jpg"
    assert "step" not in context.user_data


@pytest.mark.asyncio
async def test_polling_transport_error_is_logged_once_without_another_reply_attempt(monkeypatch):
    # PTB uses update=None for polling errors. The updater retries those
    # itself; our application error handler must not log a duplicate traceback
    # or attempt a sendMessage call over the same unavailable network.
    transport_error = handlers.NetworkError("DNS lookup failed")
    context = SimpleNamespace(error=transport_error)
    warning = MagicMock()
    monkeypatch.setattr(handlers.logger, "warning", warning)

    await handlers.on_error(None, context)

    warning.assert_called_once()
    assert "polling will retry" in warning.call_args.args[0]
