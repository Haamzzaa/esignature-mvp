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
        self._prewarm_insightface()

    def _prewarm_insightface(self):
        import os, time
        from django.conf import settings
        
        is_debug = getattr(settings, "DEBUG", False)

        if is_debug:
            # Avoid duplicate logging in StatReloader parent process
            if os.environ.get("RUN_MAIN") != "true":
                return
            logger.info(
                "[Startup] Development mode detected. "
                "Skipping InsightFace pre-warming. "
                "Models will initialize lazily on first biometric request."
            )
            return

        logger.info("[Startup] Production mode detected. Prewarming InsightFace...")
        t_start = time.perf_counter()
        try:
            from services.enterprise_biometric_service import get_face_analysis_app
            get_face_analysis_app()
            elapsed_sec = time.perf_counter() - t_start
            logger.info("[Startup] InsightFace ready. Initialization Time: %.1f seconds", elapsed_sec)
        except Exception as exc:
            logger.exception("[Startup] Failed to prewarm InsightFace: %s", exc)
            raise

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
                "          providers.identity_ocr=%s  providers.contract_ocr=%s\n"
                "          providers.face=%s  providers.liveness=%s\n"
                "          providers.notification=%s\n"
                "          events_enabled=%s  webhooks_enabled=%s\n"
                "          event_logging=%s",
                esign_config.module_name,
                "1.0.0",
                env,
                esign_config.api_version,
                esign_config.identity_ocr_provider,
                esign_config.contract_ocr_provider,
                esign_config.face_provider,
                esign_config.liveness_provider,
                esign_config.notification_provider,
                esign_config.events_enabled,
                esign_config.webhooks_enabled,
                esign_config.event_logging_enabled,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("[Startup] Could not emit startup diagnostics: %s", exc)
