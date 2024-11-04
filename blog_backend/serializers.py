from rest_framework import serializers
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError
import jwt
from datetime import datetime, timedelta
from utils.functions import validate_redirect_url


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    redirect_url = serializers.URLField(required=True)

    def validate_redirect_url(self, value):
        return validate_redirect_url(value)

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if not user.is_active:
                raise serializers.ValidationError("This account is inactive.")
            return value
        except User.DoesNotExist:
            # Use same message to prevent email enumeration
            return value

    def create_reset_token(self, user, redirect_url):
        """Create JWT token for password reset"""
        payload = {
            'user_id': user.id,
            'email': user.email,
            'redirect_url': redirect_url,
            'exp': datetime.utcnow() + timedelta(days=settings.PASSWORD_RESET['PASSWORD_RESET_TIMEOUT_DAYS']),
            'iat': datetime.utcnow(),
            'type': 'password_reset'
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

    def save(self):
        """Handle password reset request"""
        try:
            user = User.objects.get(email=self.validated_data['email'])
            redirect_url = self.validated_data['redirect_url']
            token = self.create_reset_token(user, redirect_url)

            reset_url = f"{redirect_url}?token={token}"

            context = {
                'user': user,
                'reset_url': reset_url,
                'valid_hours': settings.PASSWORD_RESET['PASSWORD_RESET_TIMEOUT_DAYS'] * 24
            }

            subject = settings.PASSWORD_RESET['EMAIL_TEMPLATES']['reset_password_subject']

            email_body = render_to_string(
                settings.PASSWORD_RESET['EMAIL_TEMPLATES']['reset_password_email'],
                context
            )

            send_mail(
                subject,
                email_body,
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
                html_message=email_body
            )

            print(f"Password reset email sent to user: {user.id} {user.email}")
            return True

        except User.DoesNotExist:
            # Still return True to prevent email enumeration
            print(f"Password reset requested for non-existent email: {self.validated_data['email']}")
            return True
        except Exception as e:
            print(f"Error in password reset process: {str(e)}")
            raise serializers.ValidationError("Unable to process password reset request.")


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                "password_mismatch": "The two password fields didn't match."
            })

        try:
            validate_password(data['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({
                "password_validation": list(e.messages)
            })

        try:
            # Decode and verify JWT token
            payload = jwt.decode(data['token'], settings.SECRET_KEY, algorithms=['HS256'])

            if payload['type'] != 'password_reset':
                raise serializers.ValidationError({"token": "Invalid token type."})

            validate_redirect_url(payload['redirect_url'])

            user = User.objects.get(id=payload['user_id'], email=payload['email'])
            if not user.is_active:
                raise serializers.ValidationError({"token": "User account is inactive."})

            self.user = user
            return data

        except jwt.ExpiredSignatureError:
            raise serializers.ValidationError({"token": "Reset token has expired."})
        except jwt.ImmatureSignatureError:
            raise serializers.ValidationError({"token": "Reset token is immature."})
        except jwt.InvalidTokenError:
            raise serializers.ValidationError({"token": "Invalid reset token."})
        except User.DoesNotExist:
            raise serializers.ValidationError({"token": "Invalid reset token."})

    def save(self):
        try:
            self.user.set_password(self.validated_data['new_password'])
            self.user.save()
            print(f"Password reset successful for user: {self.user.id} {self.user.email}")
            return True
        except Exception as e:
            print(f"Error resetting password: {str(e)}")
            raise serializers.ValidationError("Unable to reset password.")


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'name']


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions']
