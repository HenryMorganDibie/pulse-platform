from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.core.admin_auth import require_admin
from src.core.config import settings


@pytest.fixture(autouse=True)
def _admin_secret(monkeypatch):
    monkeypatch.setattr(settings, "admin_secret", "test-admin-secret")
    yield


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_correct_secret_passes(self):
        await require_admin(authorization="Bearer test-admin-secret")  # no raise

    @pytest.mark.asyncio
    async def test_wrong_secret_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await require_admin(authorization="Bearer wrong-secret")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_header_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await require_admin(authorization="")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_header_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await require_admin(authorization="test-admin-secret")  # no "Bearer " prefix
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unconfigured_secret_is_service_unavailable(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_secret", "")
        with pytest.raises(HTTPException) as exc:
            await require_admin(authorization="Bearer anything")
        assert exc.value.status_code == 503
