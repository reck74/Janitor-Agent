"""Janitor regression for #75349: merge left a duplicate WHATSAPP_CLOUD_* block.

A ``chore(sync)`` merge kept a second, unscoped ``os.getenv`` copy of the
WhatsApp Cloud block in ``gateway/config.py::_apply_env_overrides``; it
overrode the profile secret scope with process-wide credentials. Upstream's
own tests live in ``tests/gateway/test_75349_whatsapp_multiplex_secret_scope.py``.
"""
import pytest

from agent import secret_scope as ss


@pytest.fixture(autouse=True)
def _reset_multiplex():
    ss.set_multiplex_active(False)
    yield
    ss.set_multiplex_active(False)


class TestWhatsAppCloudDuplicateEnvBlockRemoved:
    """Regression for #75349 — duplicate unscoped WHATSAPP_CLOUD_* block leaks
    cross-profile credentials.

    ``gateway/config.py::_apply_env_overrides`` previously ran the WhatsApp
    Cloud block twice: once via the scoped ``getenv`` (which honors
    ``set_secret_scope``) and once via raw ``os.getenv`` (which does not). When
    both ``os.environ`` and the active profile scope carried conflicting
    ``WHATSAPP_CLOUD_PHONE_NUMBER_ID`` / ``WHATSAPP_CLOUD_ACCESS_TOKEN`` values,
    the second pass silently overrode the scoped values with the process-wide
    ones — in a multiplexed gateway that's another profile's credentials. This
    test pins the precedence contract: the SCOPE wins now that the unscoped
    duplicate is removed.
    """

    def test_scoped_block_overrides_os_environ_for_whatsapp_cloud(
        self, tmp_path, monkeypatch
    ):
        """Scope values win over conflicting os.environ values for the
        ``Platform.WHATSAPP_CLOUD`` config built by ``_apply_env_overrides``.

        The scoped ``getenv`` block reads via ``agent.secret_scope.get_secret``
        and so returns the profile's value. The duplicate ``os.getenv`` block
        used to read directly from ``os.environ`` and overwrite it; with that
        duplicate removed, the scoped value is the one that lands in the
        config.
        """
        from gateway.config import (
            GatewayConfig,
            Platform,
            _apply_env_overrides,
        )

        monkeypatch.setenv(
            "WHATSAPP_CLOUD_PHONE_NUMBER_ID", "111111111111111"
        )
        monkeypatch.setenv(
            "WHATSAPP_CLOUD_ACCESS_TOKEN", "EAAG-osenviron-leak"
        )

        (tmp_path / ".env").write_text(
            "WHATSAPP_CLOUD_PHONE_NUMBER_ID=222222222222222\n"
            "WHATSAPP_CLOUD_ACCESS_TOKEN=EAAG-scoped-value\n"
        )
        tok = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path))
        try:
            config = GatewayConfig()
            _apply_env_overrides(config)

            assert Platform.WHATSAPP_CLOUD in config.platforms, (
                "WHATSAPP_CLOUD platform not registered — both scoped and "
                "unscoped branches are required to enable it from the env"
            )
            wa_cloud = config.platforms[Platform.WHATSAPP_CLOUD]

            assert wa_cloud.enabled is True
            assert wa_cloud.extra["phone_number_id"] == "222222222222222", (
                "Expected the scoped phone_number_id; the duplicate "
                "os.getenv block overwrote it with os.environ's value"
            )
            assert wa_cloud.extra["access_token"] == "EAAG-scoped-value", (
                "Expected the scoped access_token; the duplicate "
                "os.getenv block overwrote it with os.environ's value"
            )
        finally:
            ss.reset_secret_scope(tok)
