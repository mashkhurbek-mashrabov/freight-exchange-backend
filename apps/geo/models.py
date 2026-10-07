"""Geo model definitions."""

from django.db import models


class Country(models.Model):
    """Country reference model."""

    code = models.CharField(max_length=2, primary_key=True)
    name_i18n = models.JSONField(default=dict)
    flag_url = models.URLField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Country"
        verbose_name_plural = "Countries"
        ordering = ["code"]

    def __str__(self) -> str:
        """Return country code and English or localized name."""
        name = ""
        if isinstance(self.name_i18n, dict):
            name = (
                self.name_i18n.get("en")
                or self.name_i18n.get("ru")
                or self.name_i18n.get("uz")
                or ""
            )
        return f"{self.code} - {name}" if name else self.code


class Currency(models.Model):
    """Currency reference model."""

    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Currency"
        verbose_name_plural = "Currencies"
        ordering = ["code"]

    def __str__(self) -> str:
        """Return currency code and display name."""
        if self.name and self.name != self.code:
            return f"{self.code} ({self.name})"
        return self.code


class ExchangeRate(models.Model):
    """Exchange rate reference model."""

    base = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="base_exchange_rates",
    )
    quote = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="quote_exchange_rates",
    )
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    fetched_at = models.DateTimeField()

    class Meta:
        verbose_name = "Exchange Rate"
        verbose_name_plural = "Exchange Rates"
        ordering = ["-fetched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["base", "quote", "fetched_at"],
                name="unique_base_quote_fetched_at",
            ),
        ]
        indexes = [
            models.Index(
                fields=["base", "quote", "-fetched_at"],
                name="geo_rate_latest_idx",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation of the exchange rate."""
        return f"{self.base_id}/{self.quote_id}: {self.rate} @ {self.fetched_at}"
