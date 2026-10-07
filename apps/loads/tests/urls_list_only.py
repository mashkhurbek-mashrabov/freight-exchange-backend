"""Test root URLconf containing only loads read routes under api/v1/."""

from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("apps.loads.urls_list")),
]
