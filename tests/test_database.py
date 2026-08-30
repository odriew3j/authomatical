import sqlite3


def test_tenant_isolation_across_platforms(test_db):
    """Same numeric chat_id on telegram vs bale must never collide."""
    t_tg = test_db.get_or_create_tenant("telegram", 111)
    t_bale = test_db.get_or_create_tenant("bale", 111)
    assert t_tg != t_bale


def test_get_or_create_tenant_is_idempotent(test_db):
    t1 = test_db.get_or_create_tenant("telegram", 111)
    t2 = test_db.get_or_create_tenant("telegram", 111)
    assert t1 == t2


def test_wp_connection_roundtrip_and_isolation(test_db):
    t_tg = test_db.get_or_create_tenant("telegram", 111)
    t_bale = test_db.get_or_create_tenant("bale", 111)

    test_db.save_wp_connection(t_tg, "https://siteA.example", "secretA")
    test_db.save_wp_connection(t_bale, "https://siteB.example", "secretB")

    conn_tg = test_db.get_wp_connection(t_tg)
    conn_bale = test_db.get_wp_connection(t_bale)

    assert conn_tg == {"site_url": "https://siteA.example", "secret": "secretA"}
    assert conn_bale == {"site_url": "https://siteB.example", "secret": "secretB"}


def test_unconnected_tenant_returns_none(test_db):
    t = test_db.get_or_create_tenant("telegram", 999)
    assert test_db.get_wp_connection(t) is None


def test_secret_is_encrypted_at_rest(test_db, tmp_path):
    t = test_db.get_or_create_tenant("telegram", 111)
    test_db.save_wp_connection(t, "https://site.example", "my-plaintext-secret")

    import database.db as dbmod
    db_file = dbmod.engine.url.database
    raw = sqlite3.connect(db_file)
    row = raw.execute(
        "SELECT secret_encrypted FROM wp_connections WHERE tenant_id=?", (t,)
    ).fetchone()
    assert "my-plaintext-secret" not in row[0]


def test_delete_wp_connection(test_db):
    t = test_db.get_or_create_tenant("telegram", 111)
    test_db.save_wp_connection(t, "https://site.example", "s3cr3t")
    assert test_db.delete_wp_connection(t) is True
    assert test_db.get_wp_connection(t) is None
    assert test_db.delete_wp_connection(t) is False  # already gone
