from fastapi import APIRouter

from app.modules.ai.routes import router as ai_router
from app.modules.analytics.routes import router as analytics_router
from app.modules.auth.email_routes import router as email_auth_router
from app.modules.auth.routes import router as auth_router
from app.modules.chapters.routes import router as chapters_router
from app.modules.citations.routes import router as citations_router
from app.modules.dashboard.routes import router as dashboard_router
from app.modules.documents.routes import router as documents_router
from app.modules.folders.routes import router as folders_router
from app.modules.knowledge.dashboard_routes import router as knowledge_dashboard_router
from app.modules.knowledge.graph_routes import router as knowledge_graph_router
from app.modules.knowledge.learner_routes import router as knowledge_learner_router
from app.modules.knowledge.misconception_routes import router as knowledge_misconception_router
from app.modules.knowledge.routes import router as knowledge_router
from app.modules.recommendations.learner_routes import router as learner_recommendations_router
from app.modules.recommendations.routes import router as recommendations_router
from app.modules.research.analysis_routes import router as research_analysis_router
from app.modules.research.citation_routes import router as research_citation_router
from app.modules.research.comparison_routes import router as research_comparison_router
from app.modules.research.concept_routes import router as research_concept_router
from app.modules.research.contradiction_routes import router as research_contradiction_router
from app.modules.research.draft_routes import router as research_draft_router
from app.modules.research.gap_routes import router as research_gap_router
from app.modules.research.matrix_routes import router as research_matrix_router
from app.modules.research.paper_routes import router as research_papers_router
from app.modules.research.routes import router as research_router
from app.modules.revision.routes import card_router as revision_card_router
from app.modules.revision.routes import router as revision_router
from app.modules.search.routes import router as search_router
from app.modules.study.collection_routes import router as collection_router
from app.modules.study.flashcard_routes import router as flashcard_router
from app.modules.study.library_routes import router as library_router
from app.modules.study.quiz_routes import history_router as quiz_history_router
from app.modules.study.quiz_routes import router as quiz_router
from app.modules.study.routes import router as study_router
from app.modules.subjects.routes import router as subjects_router
from app.modules.users.routes import router as users_router
from app.modules.workspaces.routes import router as workspaces_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(email_auth_router)
router.include_router(users_router)
router.include_router(workspaces_router)
router.include_router(subjects_router)
router.include_router(folders_router)
router.include_router(chapters_router)
router.include_router(dashboard_router)
router.include_router(ai_router)
router.include_router(documents_router)
router.include_router(search_router)
router.include_router(citations_router)
router.include_router(study_router)
router.include_router(flashcard_router)
router.include_router(quiz_router)
router.include_router(quiz_history_router)
router.include_router(revision_router)
router.include_router(analytics_router)
router.include_router(recommendations_router)
router.include_router(revision_card_router)
router.include_router(collection_router)
router.include_router(library_router)
router.include_router(knowledge_router)
router.include_router(knowledge_graph_router)
router.include_router(knowledge_learner_router)
router.include_router(knowledge_dashboard_router)
router.include_router(knowledge_misconception_router)
router.include_router(learner_recommendations_router)
router.include_router(research_router)
router.include_router(research_papers_router)
router.include_router(research_analysis_router)
router.include_router(research_comparison_router)
router.include_router(research_matrix_router)
router.include_router(research_gap_router)
router.include_router(research_contradiction_router)
router.include_router(research_citation_router)
router.include_router(research_draft_router)
router.include_router(research_concept_router)
