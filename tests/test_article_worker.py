from unittest.mock import MagicMock

from clients.site_connector_client import SiteConnectorError
from workers import article_worker as worker


class FakeBroker:
    def __init__(self):
        self.redis = MagicMock()
        self.acks = []

    def ack(self, group, msg_id):
        self.acks.append((group, msg_id))
        return True


class FakeArticleBuilder:
    def __init__(self):
        self.kwargs = None

    def build_structure(self, **kwargs):
        self.kwargs = kwargs
        return {
            "title": "راهنمای عینک",
            "introduction": "<p>مقدمه</p>",
            "chapters": [{"title": "فصل <اول>", "content": "<p>محتوای فصل</p>"}],
            "conclusions": "<p>جمع‌بندی</p>",
        }


class SuccessfulSite:
    instances = []

    def __init__(self, site_url, secret):
        self.site_url = site_url
        self.secret = secret
        self.payload = None
        self.__class__.instances.append(self)

    def create_post(self, payload):
        self.payload = payload
        return {"success": True, "post_id": 31, "url": "https://tenant.example/guide"}


class FailingSite(SuccessfulSite):
    def create_post(self, payload):
        self.payload = payload
        raise SiteConnectorError("کلید امنیتی نامعتبر است")


def _install_tenant_dependencies(monkeypatch, fake_broker, fake_builder, site_class):
    site_class.instances = []
    monkeypatch.setattr(worker, "broker", fake_broker)
    monkeypatch.setattr(worker, "article_builder", fake_builder)
    monkeypatch.setattr(worker, "get_or_create_tenant", lambda platform, chat_id: 77)
    monkeypatch.setattr(
        worker,
        "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "tenant-secret"},
    )
    monkeypatch.setattr(worker, "SiteConnectorClient", site_class)


def test_process_chain_publishes_to_originating_tenant_and_acknowledges(monkeypatch):
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    sent = MagicMock(return_value=True)
    _install_tenant_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    completed = worker.process_chain(
        "1-0",
        {
            "keywords": "راهنمای انتخاب عینک",
            "chapters": "5",
            "max_words": "500",
            "tone": "informative",
            "audience": "general",
            "platform": "telegram",
            "chat_id": "1001",
        },
    )

    assert completed is True
    assert builder.kwargs["max_tokens"] == 3750
    assert builder.kwargs["keywords"] == "راهنمای انتخاب عینک"
    site = SuccessfulSite.instances[0]
    assert site.site_url == "https://tenant.example"
    assert site.secret == "tenant-secret"
    assert site.payload["title"] == "راهنمای عینک"
    assert site.payload["status"] == "publish"
    assert "<h2>فصل &lt;اول&gt;</h2>" in site.payload["content"]
    assert "<p>جمع‌بندی</p>" in site.payload["content"]
    broker.redis.hset.assert_called_once()
    broker.redis.delete.assert_called_once_with("article_temp:1-0")
    assert broker.acks == [(worker.GROUP, "1-0")]
    assert sent.call_args.args[:2] == ("telegram", "1001")
    assert "https://tenant.example/guide" in sent.call_args.args[2]


def test_process_chain_notifies_and_acks_when_site_rejects_publish(monkeypatch):
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    sent = MagicMock(return_value=True)
    _install_tenant_dependencies(monkeypatch, broker, builder, FailingSite)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    completed = worker.process_chain(
        "2-0",
        {"keywords": "موضوع", "platform": "bale", "chat_id": "2002"},
    )

    assert completed is False
    assert broker.acks == [(worker.GROUP, "2-0")]
    # It is retained only until normal success cleanup; a failed site call
    # leaves the temporary record available for diagnosis.
    broker.redis.delete.assert_not_called()
    assert sent.call_args.args[:2] == ("bale", "2002")
    assert "کلید امنیتی نامعتبر" in sent.call_args.args[2]


def test_process_chain_never_uses_a_global_site_when_tenant_is_unconnected(monkeypatch):
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    sent = MagicMock(return_value=True)
    monkeypatch.setattr(worker, "broker", broker)
    monkeypatch.setattr(worker, "article_builder", builder)
    monkeypatch.setattr(worker, "get_or_create_tenant", lambda platform, chat_id: 88)
    monkeypatch.setattr(worker, "get_wp_connection", lambda tenant_id: None)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    completed = worker.process_chain(
        "3-0",
        {"keywords": "موضوع", "platform": "telegram", "chat_id": "3003"},
    )

    assert completed is False
    assert broker.acks == [(worker.GROUP, "3-0")]
    assert "یک خطای غیرمنتظره" in sent.call_args.args[2]


def test_invalid_job_numbers_fall_back_to_safe_defaults(monkeypatch):
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    _install_tenant_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(return_value=True))

    assert worker.process_chain(
        "4-0",
        {
            "keywords": "موضوع",
            "chapters": "not-a-number",
            "max_words": "0",
            "platform": "telegram",
            "chat_id": "4004",
        },
    )
    assert builder.kwargs["num_chapters"] == 5
    assert builder.kwargs["max_tokens"] == 3750
