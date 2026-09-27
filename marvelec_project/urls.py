# marvelec_project/urls.py
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    # Fotos de los reportes: sólo para usuarios con sesión iniciada (también en producción).
    re_path(r'^media/(?P<path>.*)$', login_required(serve), {'document_root': settings.MEDIA_ROOT}),
    path('', include('marvelec_app.urls')),
]
