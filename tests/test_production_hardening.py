import asyncio
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, DistributedLock, MessageDebouncer, get_db, get_redis
from app.graph import build_copy_graph
from app.main import app, get_compiled_graph
from app.security import hash_password, verify_password

settings = get_settings()


class TestProductionHardeningAndEdgeSecurity:
    """Suíte de testes para validação criptográfica, RBAC, deduplicação e locks distribuídos."""

    def test_pbkdf2_password_hashing(self):
        """Valida que senhas são hasheadas com PBKDF2-HMAC-SHA256 >= 600.000 iterações."""
        password = "AdminSuperSecretPassword2026!"
        hashed = hash_password(password, iterations=600_000)

        assert hashed.startswith("pbkdf2_sha256$600000$")
        assert verify_password(password, hashed)
        assert not verify_password("WrongPassword123", hashed)
        assert not verify_password("", hashed)

    @pytest.mark.asyncio
    async def test_webhook_secret_verification_enforcement(self, session_factory, test_redis, test_graph, monkeypatch):
        """Valida rejeição (401) quando o webhook secret configurado estiver ausente ou incorreto."""
        monkeypatch.setattr(settings, "WEBHOOK_SECRET", "super_webhook_secret_999")

        async def override_get_db():
            async with session_factory() as session:
                yield session

        async def override_get_redis():
            yield test_redis

        def override_get_graph():
            return test_graph

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        app.dependency_overrides[get_compiled_graph] = override_get_graph

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Sem header de secret -> 401
            resp_missing = await client.post(
                "/webhook/message",
                json={
                    "message_id": "sec_evt_1",
                    "sender_id": "5511999991111",
                    "message_text": "Olá",
                    "timestamp": "2026-11-23T10:00:00Z",
                },
            )
            assert resp_missing.status_code == 401
            assert "Assinatura do webhook ausente" in resp_missing.json()["detail"]

            # 2. Com header inválido -> 401
            resp_invalid = await client.post(
                "/webhook/message",
                headers={"X-Webhook-Secret": "wrong_secret"},
                json={
                    "message_id": "sec_evt_2",
                    "sender_id": "5511999991111",
                    "message_text": "Olá",
                    "timestamp": "2026-11-23T10:00:00Z",
                },
            )
            assert resp_invalid.status_code == 401
            assert "Assinatura do webhook inválida" in resp_invalid.json()["detail"]

            # 3. Com header correto -> 200
            resp_valid = await client.post(
                "/webhook/message",
                headers={"X-Webhook-Secret": "super_webhook_secret_999"},
                json={
                    "message_id": "sec_evt_3",
                    "sender_id": "5511999991111",
                    "message_text": "Oi",
                    "timestamp": "2026-11-23T10:00:00Z",
                },
            )
            assert resp_valid.status_code == 200

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_rbac_endpoints_protection(self, session_factory, test_redis):
        """Valida que /audit/logs e /audit/stats exigem autenticação administrativa com X-Admin-Key."""
        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Sem credenciais -> 401
            resp_no_auth = await client.get("/audit/logs")
            assert resp_no_auth.status_code == 401

            resp_no_auth_stats = await client.get("/audit/stats")
            assert resp_no_auth_stats.status_code == 401

            # Credenciais inválidas -> 401
            resp_bad_auth = await client.get("/audit/logs", headers={"X-Admin-Key": "invalid_admin_key"})
            assert resp_bad_auth.status_code == 401

            # Credencial válida -> 200
            resp_good_auth = await client.get(
                "/audit/logs",
                headers={"X-Admin-Key": settings.ADMIN_API_KEY},
            )
            assert resp_good_auth.status_code == 200
            assert isinstance(resp_good_auth.json(), list)

            # Teste com Bearer token
            resp_bearer = await client.get(
                "/audit/stats",
                headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}"},
            )
            assert resp_bearer.status_code == 200

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_evolution_webhook_discards_from_me_and_groups(self, session_factory, test_redis, test_graph):
        """Valida descarte estrito de mensagens enviadas pelo próprio bot (fromMe=True) e grupos (@g.us)."""
        async def override_get_db():
            async with session_factory() as session:
                yield session

        async def override_get_redis():
            yield test_redis

        def override_get_graph():
            return test_graph

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        app.dependency_overrides[get_compiled_graph] = override_get_graph

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. fromMe = True
            resp_bot = await client.post(
                "/webhook/evolution",
                json={
                    "event": "messages.upsert",
                    "data": {
                        "key": {"fromMe": True, "remoteJid": "5511999990001@s.whatsapp.net", "id": "msg_bot_1"},
                        "message": {"conversation": "Resposta automática"},
                    },
                },
            )
            assert resp_bot.status_code == 200
            assert resp_bot.json()["status"] == "ignored"
            assert resp_bot.json()["reason"] == "message_from_bot"

            # 2. Grupo do WhatsApp (@g.us)
            resp_group = await client.post(
                "/webhook/evolution",
                json={
                    "event": "messages.upsert",
                    "data": {
                        "key": {"fromMe": False, "remoteJid": "120363025555555555@g.us", "id": "msg_grp_1"},
                        "message": {"conversation": "Mensagem no grupo da empresa"},
                    },
                },
            )
            assert resp_group.status_code == 200
            assert resp_group.json()["status"] == "ignored"
            assert resp_group.json()["reason"] == "ignored_non_individual_chat"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_atomic_lua_distributed_lock_release(self, test_redis):
        """Valida que a trava distribuída só é liberada se o token conferir (script Lua atômico)."""
        phone = "5511988887777"
        lock1 = DistributedLock(test_redis, phone_number=phone, company_id="acme", timeout=5.0)

        # Adquire lock1
        acquired = await lock1.acquire()
        assert acquired

        # Outro processo tentando com token diferente
        fake_lock = DistributedLock(test_redis, phone_number=phone, company_id="acme", timeout=5.0)
        # Tenta liberar com token incorreto
        released_fake = await fake_lock.release()
        assert not released_fake  # Não deve liberar!

        # Lock original continua ativo
        current_token = await test_redis.get(lock1.lock_key)
        assert current_token == lock1.token

        # Liberação pelo dono correto
        released_real = await lock1.release()
        assert released_real
        assert await test_redis.get(lock1.lock_key) is None

    @pytest.mark.asyncio
    async def test_message_debouncer_fragmented_messages(self, test_redis):
        """Valida que mensagens enviadas em rajada são agregadas em um único texto pelo debouncer."""
        debouncer = MessageDebouncer(test_redis, wait_seconds=0.15, ttl_seconds=10)
        phone = "5511977776666"

        # Simula 2 mensagens em rajada
        async def send_chunk(text: str, delay: float):
            await asyncio.sleep(delay)
            return await debouncer.buffer_and_wait(phone=phone, text=text, company_id="default")

        # Mensagem 1 chega em t=0s, Mensagem 2 chega em t=0.05s
        res1, res2 = await asyncio.gather(
            send_chunk("Olá boa tarde", 0.0),
            send_chunk("quero criar um carrossel de marketing", 0.05),
        )

        # Mensagem 1 foi debounced (cedeu vez)
        is_leader1, text1 = res1
        assert not is_leader1
        assert text1 == ""

        # Mensagem 2 é a líder e agregou todo o conteúdo
        is_leader2, text2 = res2
        assert is_leader2
        assert "Olá boa tarde quero criar um carrossel de marketing" == text2
