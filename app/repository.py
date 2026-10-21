import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, MessageHistory, User


class UserRepository:
    """Async repository layer abstracting PostgreSQL interactions for Users and Message History."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_phone(self, phone_number: str) -> Optional[User]:
        """Fetch user by unique phone number."""
        stmt = select(User).where(User.phone_number == phone_number)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_or_create(
        self,
        phone_number: str,
        current_time: Optional[datetime] = None,
    ) -> Tuple[User, bool]:
        """Retrieve existing user or initialize new record in default onboarding state."""
        user = await self.get_by_phone(phone_number)
        if user:
            return user, False

        now = current_time or datetime.now()
        new_user = User(
            id=uuid.uuid4(),
            phone_number=phone_number,
            current_step="ASK_ONBOARDING",
            last_interaction_at=now,
            created_at=now,
        )
        self.session.add(new_user)
        await self.session.flush()
        return new_user, True

    async def update_user(
        self,
        user: User,
        *,
        name: Optional[str] = None,
        profession: Optional[str] = None,
        niche: Optional[str] = None,
        brand_handle: Optional[str] = None,
        format_type: Optional[str] = None,
        sub_intent: Optional[str] = None,
        current_step: Optional[str] = None,
        last_interaction_at: Optional[datetime] = None,
    ) -> User:
        """Update user profile fields and state tracking."""
        if name is not None:
            user.name = name
        if profession is not None:
            user.profession = profession
        if niche is not None:
            user.niche = niche
        if brand_handle is not None:
            user.brand_handle = brand_handle
        if format_type is not None:
            user.format_type = format_type
        if sub_intent is not None:
            user.sub_intent = sub_intent
        if current_step is not None:
            user.current_step = current_step
        if last_interaction_at is not None:
            user.last_interaction_at = last_interaction_at

        await self.session.flush()
        return user

    async def record_message(
        self,
        user_id: uuid.UUID,
        role: str,
        content: str,
        format_type: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> MessageHistory:
        """Persist message to message_history table."""
        now = created_at or datetime.now()
        msg = MessageHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            role=role,
            content=content,
            format_type=format_type,
            created_at=now,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_history(self, user_id: uuid.UUID, limit: int = 20) -> List[MessageHistory]:
        """Retrieve chronological message history for user."""
        stmt = (
            select(MessageHistory)
            .where(MessageHistory.user_id == user_id)
            .order_by(MessageHistory.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AuditRepository:
    """Async repository layer managing immutable audit logs."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_event(
        self,
        event_type: str,
        phone_number: str,
        *,
        user_id: Optional[uuid.UUID] = None,
        step_from: Optional[str] = None,
        step_to: Optional[str] = None,
        format_type: Optional[str] = None,
        sub_intent: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
        status: str = "SUCCESS",
        payload: Optional[dict] = None,
        created_at: Optional[datetime] = None,
    ) -> AuditLog:
        """Create and flush an audit record."""
        now = created_at or datetime.now()
        log_entry = AuditLog(
            id=uuid.uuid4(),
            event_type=event_type,
            phone_number=phone_number,
            user_id=user_id,
            step_from=step_from,
            step_to=step_to,
            format_type=format_type,
            sub_intent=sub_intent,
            execution_time_ms=execution_time_ms,
            status=status,
            payload=payload,
            created_at=now,
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry

    async def query_logs(
        self,
        *,
        phone_number: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AuditLog]:
        """Fetch audit records with optional filters."""
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        if phone_number:
            clean = phone_number.strip()
            stmt = stmt.where(
                (AuditLog.phone_number == clean)
                | (AuditLog.phone_number == f"+{clean}")
                | (AuditLog.phone_number == clean.lstrip("+"))
            )
        if event_type:
            stmt = stmt.where(AuditLog.event_type == event_type)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
