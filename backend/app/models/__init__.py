# Import all models so Alembic autogenerate sees the full metadata.
from app.models.activity_log import ActivityLog
from app.models.ai_usage_record import AiUsageRecord
from app.models.chapter import Chapter
from app.models.conversation import Conversation
from app.models.email_verification_token import EmailVerificationToken
from app.models.folder import Folder
from app.models.llm_provider import LLMModel, LLMModelPrice, LLMProvider
from app.models.message import Message, MessageFeedback
from app.models.password_reset_token import PasswordResetToken
from app.models.prompt_template import PromptTemplate
from app.models.session_model import Session
from app.models.subject import Subject
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.models.user_profile import UserProfile
from app.models.workspace import Workspace

__all__ = [
    "ActivityLog",
    "AiUsageRecord",
    "Chapter",
    "Conversation",
    "EmailVerificationToken",
    "Folder",
    "LLMModel",
    "LLMModelPrice",
    "LLMProvider",
    "Message",
    "MessageFeedback",
    "PasswordResetToken",
    "PromptTemplate",
    "Session",
    "Subject",
    "User",
    "UserPreferences",
    "UserProfile",
    "Workspace",
]
