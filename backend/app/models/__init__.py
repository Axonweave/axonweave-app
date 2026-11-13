# Import all models so Alembic autogenerate sees the full metadata.
from app.models.activity_log import ActivityLog
from app.models.ai_usage_record import AiUsageRecord
from app.models.chapter import Chapter
from app.models.conversation import Conversation
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_job import DocumentProcessingJob
from app.models.email_verification_token import EmailVerificationToken
from app.models.flashcard import Flashcard, FlashcardSet
from app.models.folder import Folder
from app.models.generation_job import GenerationJob
from app.models.knowledge import (
    KnowledgeDuplicateCandidate,
    KnowledgeEdge,
    KnowledgeEvidence,
    KnowledgeExtractionJob,
    KnowledgeMergeHistory,
    KnowledgeNode,
    KnowledgeNodeAlias,
)
from app.models.llm_provider import LLMModel, LLMModelPrice, LLMProvider
from app.models.message import Message, MessageFeedback
from app.models.message_citation import MessageCitation
from app.models.password_reset_token import PasswordResetToken
from app.models.prompt_template import PromptTemplate
from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.models.revision import (
    FlashcardReview,
    FlashcardScheduling,
    RevisionRecommendation,
    RevisionSession,
)
from app.models.session_model import Session
from app.models.storage_cleanup import StorageCleanup
from app.models.study_export import StudyExport
from app.models.study_material import StudyMaterial, StudyMaterialVersion
from app.models.study_preferences import StudyGenerationPreferences
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
    "Document",
    "DocumentChunk",
    "DocumentProcessingJob",
    "DocumentVersion",
    "EmailVerificationToken",
    "Folder",
    "FlashcardReview",
    "FlashcardScheduling",
    "RevisionRecommendation",
    "RevisionSession",
    "Flashcard",
    "FlashcardSet",
    "GenerationJob",
    "KnowledgeDuplicateCandidate",
    "KnowledgeEdge",
    "KnowledgeEvidence",
    "KnowledgeExtractionJob",
    "KnowledgeMergeHistory",
    "KnowledgeNode",
    "KnowledgeNodeAlias",
    "LLMModel",
    "LLMModelPrice",
    "LLMProvider",
    "Message",
    "MessageCitation",
    "MessageFeedback",
    "PasswordResetToken",
    "PromptTemplate",
    "Quiz",
    "QuizAttempt",
    "QuizAttemptAnswer",
    "QuizQuestion",
    "Session",
    "StorageCleanup",
    "StudyExport",
    "StudyGenerationPreferences",
    "StudyMaterial",
    "StudyMaterialVersion",
    "Subject",
    "User",
    "UserPreferences",
    "UserProfile",
    "Workspace",
]
