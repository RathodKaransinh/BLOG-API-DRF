import re
from django.conf import settings
from rest_framework import serializers


def validate_redirect_url(url):
    """Validate redirect URL against allowed patterns"""
    if not url:
        raise serializers.ValidationError("Redirect URL is required.")

    # Check URL against allowed patterns
    for pattern in settings.PASSWORD_RESET['ALLOWED_URL_PATTERNS']:
        if re.match(pattern, url):
            return url

    raise serializers.ValidationError("Invalid redirect URL format.")
