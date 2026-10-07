"""Serializers for geo reference data."""

from rest_framework import serializers

from apps.geo.models import Country, Currency, ExchangeRate


class CountrySerializer(serializers.ModelSerializer):
    """Country serializer exposing ISO code, localized names, and flag URL."""

    class Meta:
        model = Country
        fields = ["code", "name_i18n", "flag_url"]


class CurrencySerializer(serializers.ModelSerializer):
    """Currency serializer exposing ISO 4217 code and display name."""

    class Meta:
        model = Currency
        fields = ["code", "name"]


class ExchangeRateSerializer(serializers.ModelSerializer):
    """Exchange rate serializer exposing base, quote, rate, and fetch timestamp."""

    base = serializers.SlugRelatedField(
        slug_field="code",
        read_only=True,
        help_text="Base currency code (e.g. USD).",
    )
    quote = serializers.SlugRelatedField(
        slug_field="code",
        read_only=True,
        help_text="Quote currency code (e.g. UZS).",
    )

    class Meta:
        model = ExchangeRate
        fields = ["base", "quote", "rate", "fetched_at"]
