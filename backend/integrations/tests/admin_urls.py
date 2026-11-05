"""The app's URLs plus the admin, which is otherwise mounted only when DEBUG is on (D41)."""

from django.contrib import admin
from django.urls import path

from config.urls import urlpatterns as app_urls

urlpatterns = [*app_urls, path("admin/", admin.site.urls)]
