from database.db import SessionLocal
from database.models import Tenant, WPConnection
from database.crypto import encrypt, decrypt


def get_or_create_tenant(platform: str, chat_id, display_name: str = None) -> int:
    """Returns the tenant_id for (platform, chat_id), creating the row on
    first contact. This is the single point that ties a bot conversation
    to a specific user's own data — every DB read/write for that
    conversation goes through this tenant_id, so one person's site
    credentials are never visible to another person's session."""
    chat_id = str(chat_id)
    with SessionLocal() as session:
        tenant = (
            session.query(Tenant)
            .filter_by(platform=platform, platform_chat_id=chat_id)
            .first()
        )
        if tenant:
            if display_name and tenant.display_name != display_name:
                tenant.display_name = display_name
                session.commit()
            return tenant.id

        tenant = Tenant(platform=platform, platform_chat_id=chat_id, display_name=display_name)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant.id


def save_wp_connection(tenant_id: int, site_url: str, secret: str, verified: bool = True) -> None:
    with SessionLocal() as session:
        conn = session.query(WPConnection).filter_by(tenant_id=tenant_id).first()
        enc_secret = encrypt(secret)
        if conn:
            conn.site_url = site_url
            conn.secret_encrypted = enc_secret
            conn.verified = verified
        else:
            conn = WPConnection(
                tenant_id=tenant_id,
                site_url=site_url,
                secret_encrypted=enc_secret,
                verified=verified,
            )
            session.add(conn)
        session.commit()


def get_wp_connection(tenant_id: int) -> dict | None:
    """Returns {'site_url': ..., 'secret': ...} for a verified connection,
    or None if this tenant hasn't connected a site yet."""
    with SessionLocal() as session:
        conn = (
            session.query(WPConnection)
            .filter_by(tenant_id=tenant_id, verified=True)
            .first()
        )
        if not conn:
            return None
        return {"site_url": conn.site_url, "secret": decrypt(conn.secret_encrypted)}


def delete_wp_connection(tenant_id: int) -> bool:
    with SessionLocal() as session:
        conn = session.query(WPConnection).filter_by(tenant_id=tenant_id).first()
        if not conn:
            return False
        session.delete(conn)
        session.commit()
        return True
