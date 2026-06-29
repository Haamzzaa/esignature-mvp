from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from esign.health_views import live_view, ready_view, health_view
from esign.views import ProtectedMediaView

# Define versioned OpenAPI/Swagger view
schema_view = get_schema_view(
    openapi.Info(
        title="E-Signature Platform API",
        default_version='v1',
        description="API documentation for the E-Signature Platform",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    patterns=[
        path('api/v1/', include('esign.urls')),
    ],
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Observability: health probes (no auth, root-level) ──
    path('live', live_view, name='liveness'),
    path('ready', ready_view, name='readiness'),
    path('health', health_view, name='health'),

    # Swagger/OpenAPI documentation paths under api/v1
    path('api/v1/swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('api/v1/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/v1/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    # Legacy unversioned API (keep operational for backward compatibility)
    path('api/', include('esign.urls')),

    # Versioned API (v1)
    path('api/v1/', include('esign.urls')),
    
    # Intercept all media requests and route through ProtectedMediaView
    path('media/<path:path>', ProtectedMediaView.as_view(), name='protected-media'),
]