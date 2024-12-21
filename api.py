from fastapi import FastAPI
from pydantic import BaseModel, EmailStr
from typing import Optional
from main import AccountRegistration
import uvicorn

app = FastAPI(title="账号注册服务")

class RegistrationRequest(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: EmailStr

class RegistrationResponse(BaseModel):
    success: bool
    error: Optional[str] = None

@app.post("/register", response_model=RegistrationResponse)
async def register_account(request: RegistrationRequest) -> RegistrationResponse:
    """
    注册新账号
    
    参数:
    - first_name: 名
    - last_name: 姓
    - username: 用户名
    - email: 电子邮件
    
    返回:
    - success: 是否成功
    - error: 错误信息（如果失败）
    """
    registration = AccountRegistration()
    success, error = registration.register_account(
        first_name=request.first_name,
        last_name=request.last_name,
        username=request.username,
        email=str(request.email)
    )
    
    return RegistrationResponse(success=success, error=error)

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
