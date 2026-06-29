import logging
from django.apps import AppConfig

logger = logging.getLogger("esign.startup")


class EsignConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'esign'

    def ready(self):
        from esign.events.registry import register_built_in_handlers
        register_built_in_handlers()
        self._emit_startup_diagnostics()

    def _emit_startup_diagnostics(self):
        """
        Emits a concise one-time startup summary to the log.
        Covers: module metadata, active providers, event/webhook status.
        Never logs secrets or credentials.
        """
        try:
            from django.conf import settings
            from esign.config import esign_config

            env = "production" if not getattr(settings, "DEBUG", False) else "development"

            logger.info(
                "[Startup] ╔══════════════════════════════════════════════╗\n"
                "          ║     E-Signature Module — Startup Diagnostics  ║\n"
                "          ╚══════════════════════════════════════════════╝\n"
                "          module=%s  version=%s  environment=%s\n"
                "          api_version=%s\n"
                "          providers.ocr=%s  providers.face=%s\n"
                "          providers.liveness=%s  providers.notification=%s\n"
                "          events_enabled=%s  webhooks_enabled=%s\n"
                "          event_logging=%s",
                esign_config.module_name,
                "1.0.0",
                env,
                esign_config.api_version,
                esign_config.ocr_provider,
                esign_config.face_provider,
                esign_config.liveness_provider,
                esign_config.notification_provider,
                esign_config.events_enabled,
                esign_config.webhooks_enabled,
                esign_config.event_logging_enabled,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("[Startup] Could not emit startup diagnostics: %s", exc)
