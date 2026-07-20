"""登录注册相关请求与响应模型。"""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


VerificationPurpose = Literal["register", "login"]


class SendVerificationCodeRequest(BaseModel):
    email: EmailStr
    purpose: VerificationPurpose


class SendVerificationCodeResponse(BaseModel):
    message: str
    expires_in_seconds: int
    resend_after_seconds: int
    debug_code: str | None = None


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)
    verification_code: str = Field(min_length=4, max_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    verification_code: str = Field(min_length=4, max_length=8)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    username: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
