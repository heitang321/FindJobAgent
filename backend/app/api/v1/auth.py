"""登录注册认证接口。"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.core.config import settings
from app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    RegisterRequest,
    SendVerificationCodeRequest,
    SendVerificationCodeResponse,
    UserResponse,
)
from app.services.auth_repository import user_repository
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.services.email_sender import EmailSendError
from app.services.verification_codes import verification_code_manager

router = APIRouter()


@router.post(
    "/send-code",
    response_model=SendVerificationCodeResponse,
    summary="发送邮箱验证码",
)
async def send_verification_code(
    payload: SendVerificationCodeRequest,
) -> SendVerificationCodeResponse:
    email = payload.email.casefold()
    user = user_repository.get_by_email(email)
    if payload.purpose == "register" and user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册，请直接登录",
        )
    if payload.purpose == "login" and user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该邮箱尚未注册，请先注册",
        )

    try:
        code = verification_code_manager.issue(
            email=email, purpose=payload.purpose
        )
    except EmailSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"验证码邮件发送失败：{exc}",
        ) from exc

    return SendVerificationCodeResponse(
        message="验证码已发送",
        expires_in_seconds=settings.AUTH_VERIFICATION_EXPIRE_SECONDS,
        resend_after_seconds=settings.AUTH_VERIFICATION_RESEND_SECONDS,
        debug_code=code
        if settings.DEBUG and settings.AUTH_DEBUG_RETURN_CODE
        else None,
    )


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    summary="邮箱验证码注册",
)
async def register(payload: RegisterRequest) -> AuthTokenResponse:
    email = payload.email.casefold()
    if payload.password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="两次输入的密码不一致",
        )
    if user_repository.get_by_email(email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册，请直接登录",
        )
    if not verification_code_manager.verify(
        email=email, purpose="register", code=payload.verification_code
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期",
        )

    user = user_repository.create_user(
        email=email,
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    return AuthTokenResponse(
        access_token=create_access_token(user),
        user=UserResponse(**user.public_dict()),
    )


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    summary="邮箱验证码登录",
)
async def login(payload: LoginRequest) -> AuthTokenResponse:
    email = payload.email.casefold()
    user = user_repository.get_by_email(email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    if not verification_code_manager.verify(
        email=email, purpose="login", code=payload.verification_code
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期",
        )

    return AuthTokenResponse(
        access_token=create_access_token(user),
        user=UserResponse(**user.public_dict()),
    )


@router.get("/me", summary="获取当前用户信息")
async def get_me(user: CurrentUser) -> dict:
    """返回当前登录用户信息。"""
    return user
