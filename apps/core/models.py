"""Core model definitions."""

from django.db import models


class BaseModel(models.Model):
    """Abstract base model tracking creation and update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
