import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import bcrypt
import jwt
from asyncpg import UniqueViolationError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

import ai_analyzer
import aws_scanner
import db
from ai_analyzer import OpenAIKeyMissingError, OpenAIRequestError
from aws_scanner import (
    AWSCLICommandError,
    AWSCLINotInstalledError,
    AWSCredentialsExpiredError,
    AWSNotConfiguredError,
    InvalidResourceGroupError,
)

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


app = FastAPI(title="AI Cloud Cost Detective - AWS Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    resource_group: str
    analysis_id: Optional[str] = None


class SignupRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) < 3:
            raise ValueError("A valid email is required.")
        return value

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


def _create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(authorization: Optional[str]) -> Optional[int]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def get_current_user_required(authorization: Optional[str] = Header(None)) -> int:
    user_id = _decode_token(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user_id


class ProgressManager:
    """Tracks WebSocket listeners per analysis id and broadcasts progress to them."""

    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, analysis_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(analysis_id, []).append(websocket)

    def disconnect(self, analysis_id: str, websocket: WebSocket) -> None:
        connections = self._connections.get(analysis_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                self._connections.pop(analysis_id, None)

    async def send(self, analysis_id: str, message: Dict[str, Any]) -> None:
        for websocket in list(self._connections.get(analysis_id, [])):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(analysis_id, websocket)


progress_manager = ProgressManager()


def _handle_scanner_errors(exc: Exception) -> None:
    if isinstance(exc, AWSCLINotInstalledError):
        raise HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, AWSNotConfiguredError):
        raise HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, AWSCredentialsExpiredError):
        raise HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, InvalidResourceGroupError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AWSCLICommandError):
        raise HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, OpenAIKeyMissingError):
        raise HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, OpenAIRequestError):
        raise HTTPException(status_code=502, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/auth/signup")
async def signup(request: SignupRequest):
    existing = await db.get_user_by_email(request.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    password_hash = bcrypt.hashpw(request.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        user_id = await db.create_user(request.email, password_hash)
    except UniqueViolationError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    token = _create_access_token(user_id)
    return {"token": token, "user": {"id": user_id, "email": request.email}}


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    user = await db.get_user_by_email(request.email.strip().lower())
    if user is None or not bcrypt.checkpw(
        request.password.encode("utf-8"), user["password_hash"].encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = _create_access_token(user["id"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"]}}


@app.get("/api/resource-groups")
def get_resource_groups(user_id: int = Depends(get_current_user_required)):
    try:
        groups = aws_scanner.list_resource_groups()
    except aws_scanner.AWSScannerError as exc:
        _handle_scanner_errors(exc)
    return {"resource_groups": groups}


@app.websocket("/ws/progress/{analysis_id}")
async def progress_ws(websocket: WebSocket, analysis_id: str):
    await progress_manager.connect(analysis_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        progress_manager.disconnect(analysis_id, websocket)


@app.post("/api/analyze")
async def analyze(
    request: AnalyzeRequest,
    user_id: int = Depends(get_current_user_required),
):
    resource_group = request.resource_group.strip()
    if not resource_group:
        raise HTTPException(status_code=400, detail="resource_group is required.")

    analysis_id = request.analysis_id or str(uuid4())
    await db.create_analysis(analysis_id, user_id, resource_group)

    try:
        await progress_manager.send(
            analysis_id, {"stage": "starting", "message": "Fetching resource groups..."}
        )

        await progress_manager.send(
            analysis_id,
            {"stage": "scanning", "message": f"Scanning resources in {resource_group}..."},
        )
        resources = await asyncio.to_thread(
            aws_scanner.get_resources_in_group, resource_group
        )

        await progress_manager.send(
            analysis_id, {"stage": "analyzing", "message": "Analyzing costs with AI..."}
        )
        analysis = await asyncio.to_thread(ai_analyzer.analyze_resources, resources)

        await progress_manager.send(
            analysis_id, {"stage": "storing", "message": "Storing results..."}
        )
        issues = analysis.get("issues", [])
        try:
            total_savings = float(analysis.get("total_estimated_monthly_savings_usd") or 0)
        except (TypeError, ValueError):
            total_savings = 0.0
        await db.complete_analysis(
            analysis_id,
            resources_scanned=len(resources),
            issues_found=len(issues),
            estimated_savings=f"${total_savings:,.2f}/month",
            analysis_result=analysis,
        )

        await progress_manager.send(
            analysis_id, {"stage": "complete", "message": "Analysis complete"}
        )
    except (aws_scanner.AWSScannerError, ai_analyzer.AIAnalyzerError) as exc:
        await db.fail_analysis(analysis_id, str(exc))
        await progress_manager.send(analysis_id, {"stage": "error", "message": str(exc)})
        _handle_scanner_errors(exc)

    return {
        "analysis_id": analysis_id,
        "resource_group": resource_group,
        "resources": resources,
        "analysis": analysis,
    }


@app.get("/api/history")
async def get_history(user_id: int = Depends(get_current_user_required)):
    history = await db.get_history(user_id)
    return {"history": history}
