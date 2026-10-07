"""Views for accounts and authentication endpoints."""

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts import services
from apps.accounts.models import Company
from apps.accounts.serializers import (
    CompanySerializer,
    DeviceSerializer,
    LogoutSerializer,
    OtpRequestSerializer,
    OtpVerifyResponseSerializer,
    OtpVerifySerializer,
    TokenRefreshResponseSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.core.serializers import ErrorSerializer


@extend_schema(
    tags=["Auth"],
    summary="Request OTP code",
    description="Send a 6-digit OTP code to the given phone number via SMS.",
    request=OtpRequestSerializer,
    responses={
        204: None,
        400: ErrorSerializer,
        429: ErrorSerializer,
    },
    examples=[
        OpenApiExample(
            name="OTP Request Example",
            summary="Example OTP request with phone number",
            value={"phone": "+998900000001"},
            request_only=True,
        ),
    ],
)
class OtpRequestView(APIView):
    """Endpoint to request an OTP code for login/registration."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_otp(serializer.validated_data["phone"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["Auth"],
    summary="Verify OTP code",
    description="Verify 6-digit OTP code, authenticate user, and issue JWT tokens.",
    request=OtpVerifySerializer,
    responses={
        200: OtpVerifyResponseSerializer,
        400: ErrorSerializer,
        403: ErrorSerializer,
    },
    examples=[
        OpenApiExample(
            name="OTP Verify Example",
            summary="Example OTP verify with dev code",
            value={"phone": "+998900000001", "code": "000000"},
            request_only=True,
        ),
    ],
)
class OtpVerifyView(APIView):
    """Endpoint to verify OTP code and obtain JWT authentication tokens."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.verify_otp(
            phone=serializer.validated_data["phone"],
            code=serializer.validated_data["code"],
        )
        response_serializer = OtpVerifyResponseSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Auth"],
    summary="Refresh JWT access token",
    description="Obtain a fresh JWT access token using a valid refresh token.",
    responses={
        200: TokenRefreshResponseSerializer,
        401: ErrorSerializer,
    },
)
class TokenRefreshCustomView(TokenRefreshView):
    """Endpoint to refresh access token using refresh token."""

    permission_classes = [AllowAny]


@extend_schema(
    tags=["Auth"],
    summary="Logout user",
    description="Blacklist refresh token to invalidate active session.",
    request=LogoutSerializer,
    responses={
        204: None,
        400: ErrorSerializer,
        401: ErrorSerializer,
    },
)
class LogoutView(APIView):
    """Endpoint to log out by blacklisting the refresh token."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.logout(serializer.validated_data["refresh"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Endpoint to view and update the authenticated user's profile."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        tags=["Profile"],
        summary="Get current user profile",
        description="Retrieve profile details of the authenticated user.",
        responses={
            200: UserSerializer,
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Profile"],
        summary="Update current user profile",
        description=(
            "Update profile fields (full_name, role, language, avatar). "
            "Phone and status are read-only."
        ),
        request=UserUpdateSerializer,
        responses={
            200: UserSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
        },
    )
    def patch(self, request: Request) -> Response:
        serializer = UserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = services.update_profile(request.user, **serializer.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Profile"],
    summary="Create or update company",
    description="Create or update the company profile for the authenticated user.",
    request=CompanySerializer,
    responses={
        200: CompanySerializer,
        400: ErrorSerializer,
        401: ErrorSerializer,
        409: ErrorSerializer,
    },
)
class MeCompanyView(APIView):
    """Endpoint to create or update user company."""

    permission_classes = [IsAuthenticated]

    def put(self, request: Request) -> Response:
        instance = None
        try:
            if hasattr(request.user, "company"):
                instance = request.user.company
        except Company.DoesNotExist:
            instance = None

        serializer = CompanySerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        company, _ = services.upsert_company(
            user=request.user,
            data=serializer.validated_data,
        )
        return Response(CompanySerializer(company).data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Profile"],
    summary="Register FCM device token",
    description="Register or update FCM device token, associating it with current user.",
    request=DeviceSerializer,
    responses={
        200: DeviceSerializer,
        201: DeviceSerializer,
        400: ErrorSerializer,
        401: ErrorSerializer,
    },
)
class MeDeviceView(APIView):
    """Endpoint to register or update mobile device FCM token."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, created = services.register_device(
            user=request.user,
            fcm_token=serializer.validated_data["fcm_token"],
            platform=serializer.validated_data["platform"],
        )
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(DeviceSerializer(device).data, status=status_code)


@extend_schema(
    tags=["Profile"],
    summary="Remove device token",
    description="Delete device registration for the current user by FCM token.",
    responses={
        204: None,
        401: ErrorSerializer,
    },
)
class MeDeviceDeleteView(APIView):
    """Endpoint to delete a registered device token."""

    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, token: str) -> Response:
        services.delete_device(user=request.user, fcm_token=token)
        return Response(status=status.HTTP_204_NO_CONTENT)
