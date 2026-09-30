from django.urls import path

from .health import live, ready

urlpatterns = [path("health/live", live), path("health/ready", ready)]
