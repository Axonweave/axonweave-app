Let's make Phase 2 the foundation of the entire AI intelligence system in Axonweave AI. This is important: we are not simply adding a chatbot. We are building a reusable AI infrastructure that future modules—document intelligence, tutoring, flashcards, assessments, research analysis and adaptive learning—will all use.

The following is the complete implementation specification.

# Axonweave AI

# Phase 2 — AI Foundation and LLM Integration

## Complete Technical and Development Specification

**Project:** Axonweave AI\
**Phase:** 2 — AI Foundation and LLM Integration\
**Prerequisite:** Phase 1 — Application Foundation\
**Architecture:** Modular monolith with provider-independent AI services\
**Primary objective:** Build a secure, extensible AI infrastructure that integrates existing LLMs into Axonweave AI and provides a common intelligence layer for all future AI-powered features.

---

# 1. Project Overview

## 1.1 Purpose

Phase 1 established the application foundation:

- User authentication.
- User profiles.
- Dashboard.
- Workspaces.
- Subjects.
- Folders.
- Chapters.
- PostgreSQL database.
- FastAPI backend.
- Next.js frontend.
- Application security and access control.

Phase 2 will introduce the AI intelligence layer.

Axonweave AI will use existing Large Language Models through APIs or locally hosted inference rather than attempting to train a foundation model from scratch.

The application must own the orchestration, context management, conversation management, prompts, model selection, security, usage tracking and AI-specific workflows.

## 1.2 Main objectives

Implement:

1. LLM provider integration.
2. Provider-independent AI architecture.
3. AI orchestration service.
4. Model configuration and selection.
5. AI Tutor interface.
6. Conversation management.
7. Message persistence.
8. Streaming AI responses.
9. Conversation context management.
10. System prompt management.
11. Token and usage tracking.
12. API cost estimation.
13. Error handling and retries.
14. AI-specific security.
15. AI service testing and evaluation.

## 1.3 What Axonweave should achieve

At the end of Phase 2, a user should be able to:

1. Log in to Axonweave AI.
2. Open the AI Tutor.
3. Start a new conversation.
4. Select an available model, if model selection is enabled.
5. Ask an academic or general question.
6. Receive a streamed AI response.
7. Continue the conversation with contextual follow-up questions.
8. Refresh the page and retrieve the conversation.
9. Rename or delete conversations.
10. Switch between conversations.
11. View basic usage information.

The AI Tutor should be a genuine working application feature, not a hardcoded chatbot demonstration.

---

# 2. Important Architectural Decisions

Before development, establish these decisions.

## 2.1 We are not building our own foundation LLM

We will use existing models.

Potential providers:

- OpenAI.
- Google Gemini.
- Anthropic Claude.
- Locally hosted open-weight models.

The first implementation should support one primary provider. The architecture must allow additional providers without requiring a complete backend rewrite.

## 2.2 The LLM is not the application backend

The LLM is an external intelligence service.

Axonweave's backend remains responsible for:

- Authentication.
- Authorization.
- Conversation storage.
- Message persistence.
- User data.
- Context construction.
- Prompt construction.
- Model selection.
- Tool execution.
- Usage tracking.
- Cost tracking.
- Security.
- Error handling.

The LLM receives only the information required for a particular request.

## 2.3 Never call an LLM directly from the frontend

The correct request flow is:

```
User
 |
 v
Axonweave Frontend
 |
 v
Axonweave FastAPI Backend
 |
 v
Authentication and Authorization
 |
 v
AI Orchestration Service
 |
 v
LLM Provider Adapter
 |
 v
External LLM API
 |
 v
Axonweave Backend
 |
 v
Frontend
```

API keys and provider credentials must remain on the backend.

## 2.4 Provider-independent architecture

The application must not depend on one provider's proprietary request format throughout the codebase.

Instead, implement a common interface.

```
Axonweave AI Service
          |
          v
   Provider Interface
          |
     +----+----+
     |    |    |
     v    v    v
   OpenAI Gemini Claude
```

A future provider can be integrated by implementing the same interface and its required capabilities.

## 2.5 Do not introduce unnecessary infrastructure

For Phase 2:

- Continue using PostgreSQL.
- Continue using SQLAlchemy and Alembic.
- Use the existing FastAPI backend.
- Use the existing Next.js frontend.
- Use the existing authentication and authorization infrastructure.
- Add Redis only if required for rate limiting, distributed coordination or other justified workloads.
- Do not introduce microservices.
- Do not introduce Kubernetes.
- Do not introduce a separate vector database yet.
- Do not implement RAG yet.

---

# 3. Technology Stack

Continue using the Phase 1 stack.

| Component        | Technology                    | Responsibility          |
| ---------------- | ----------------------------- | ----------------------- |
| Frontend         | Next.js                       | Application interface   |
| UI               | React                         | Components              |
| Language         | TypeScript                    | Type safety             |
| Styling          | Tailwind CSS                  | Styling                 |
| UI components    | shadcn/ui                     | Interface components    |
| Backend          | FastAPI                       | API and business logic  |
| Database         | PostgreSQL                    | Persistent storage      |
| ORM              | SQLAlchemy                    | Database interaction    |
| Migrations       | Alembic                       | Schema migrations       |
| Validation       | Pydantic                      | Data validation         |
| AI integration   | Provider SDKs or HTTP clients | Model communication     |
| Streaming        | Server-Sent Events            | Streaming responses     |
| Testing          | Pytest                        | Backend testing         |
| Frontend testing | Playwright                    | UI and workflow testing |
| Containers       | Docker                        | Consistent environment  |

Potential additional libraries:

- `openai` for OpenAI API integration.
- `google-genai` for Google Gemini.
- `anthropic` for Anthropic Claude.
- `httpx` for asynchronous HTTP requests where required.
- `tiktoken` or provider-specific token counting utilities where applicable.

Do not install every provider SDK immediately. Start with the selected primary provider.

Pin dependencies and verify SDK compatibility before implementation.

---

# 4. AI System Architecture

## 4.1 High-level architecture

```
                    USER
                     |
                     v
             NEXT.JS FRONTEND
                     |
                     v
               FASTAPI BACKEND
                     |
                     v
           AUTHENTICATION LAYER
                     |
                     v
            AI ORCHESTRATION
                     |
          +----------+-----------+
          |          |           |
          v          v           v
     Context     Prompt       Model
    Management  Management   Selection
          |          |           |
          +----------+-----------+
                     |
                     v
             PROVIDER ADAPTER
                     |
          +----------+-----------+
          |          |           |
          v          v           v
        OPENAI     GEMINI      CLAUDE
                     |
                     v
             RESPONSE HANDLER
                     |
          +----------+-----------+
          |          |           |
          v          v           v
       Streaming  Persistence  Usage
          |          |           |
          +----------+-----------+
                     |
                     v
              FRONTEND DISPLAY
```

## 4.2 Main backend components

Implement these independent modules.

### A. Provider management

Responsible for:

- Provider registration.
- Provider configuration.
- Model availability.
- Provider authentication.
- Provider-specific request formatting.
- Provider-specific response parsing.

### B. AI orchestration

Responsible for:

- Receiving AI requests.
- Validating requests.
- Selecting a model.
- Constructing context.
- Selecting prompts.
- Invoking providers.
- Processing responses.
- Handling errors.
- Recording usage.

### C. Conversation management

Responsible for:

- Creating conversations.
- Retrieving conversations.
- Updating titles.
- Deleting conversations.
- Listing user conversations.
- Managing conversation ownership.

### D. Message management

Responsible for:

- Saving user messages.
- Saving assistant messages.
- Maintaining message order.
- Tracking message status.
- Recording token usage.
- Retrieving conversation history.

### E. Context management

Responsible for:

- Retrieving previous messages.
- Applying context limits.
- Selecting relevant history.
- Preparing provider-compatible message sequences.
- Avoiding unbounded conversation history.

### F. Prompt management

Responsible for:

- System instructions.
- Tutor behaviour.
- Response formatting.
- Model-specific adaptations.
- Prompt versioning.

### G. Usage management

Responsible for:

- Tracking requests.
- Tracking input tokens.
- Tracking output tokens.
- Estimating costs.
- Tracking failures.
- Monitoring usage per user and model.

---

# 5. LLM Provider Integration

## 5.1 Provider selection

The first task is to choose one primary provider.

Evaluate providers based on:

- Answer quality.
- Reasoning ability.
- Context-window size.
- Streaming support.
- Structured output support.
- Tool calling support.
- Multimodal capabilities.
- API pricing.
- Rate limits.
- Availability in the deployment region.
- Data retention and privacy terms.
- SDK maturity.

Do not choose a provider only because it has the cheapest model.

Axonweave will eventually perform several different tasks, and model quality may differ across those tasks.

## 5.2 Initial implementation

For the first working version:

- Integrate one provider.
- Support one or more explicitly configured models.
- Keep the model identifier in backend configuration.
- Test normal responses.
- Test streaming responses.
- Test failures and rate limits.
- Record usage.

Do not hardcode the provider name in conversation routes or frontend components.

## 5.3 Provider interface

Create a common provider contract.

Illustrative Python interface:

```
from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):

    @abstractmethod
    async def generate(self, request):
        pass

    @abstractmethod
    async def stream(self, request) -> AsyncIterator:
        pass

    @abstractmethod
    async def generate_structured(self, request, schema):
        pass
```

Define standard request and response types.

Example request:

```
class LLMRequest:
    model: str
    messages: list
    temperature: float | None
    max_output_tokens: int
    metadata: dict
```

Example response:

```
class LLMResponse:
    content: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None
    provider_request_id: str | None
```

These are illustrative interfaces. Use Pydantic models or typed dataclasses in the actual implementation.

Provider adapters should convert the common request into the appropriate provider format and normalise the returned response.

## 5.4 Provider adapters

Create separate adapters.

```
ai/
|
+-- providers/
|   |
|   +-- base.py
|   +-- openai_provider.py
|   +-- gemini_provider.py
|   +-- anthropic_provider.py
|   +-- local_provider.py
```

Initially, implement only the selected provider.

Each adapter must handle:

- Authentication.
- Request construction.
- Response parsing.
- Streaming.
- Usage extraction.
- Provider errors.
- Timeouts.
- Rate limits.

Do not return raw provider SDK response objects to the frontend.

## 5.5 Provider configuration

Provider credentials must be configured on the server.

Example:

```
LLM_PROVIDER=openai
LLM_DEFAULT_MODEL=your_configured_model

OPENAI_API_KEY=replace_with_secret

LLM_TIMEOUT_SECONDS=60
LLM_MAX_OUTPUT_TOKENS=2000
```

The actual model ID must be verified against the provider's currently available API models.

Do not assume a model name remains available indefinitely.

Never commit populated environment files.

---

# 6. Model Configuration and Selection

Create a model registry inside the backend.

The registry should define the models the application is allowed to use.

Example configuration:

```
AVAILABLE_MODELS = {
    "default": {
        "provider": "openai",
        "model": "configured-model-id",
        "capabilities": [
            "chat",
            "streaming"
        ]
    }
}
```

This is an illustrative configuration, not a literal provider model identifier.

## 6.1 Model configuration fields

Each model configuration should contain:

- Internal model identifier.
- Provider.
- Provider model ID.
- Display name.
- Active status.
- Supported capabilities.
- Input token limit, if verified.
- Output token limit, if verified.
- Pricing metadata, if known.
- Default temperature, where supported.
- Configuration version.

## 6.2 Model selection

For Phase 2, provide:

- Default model.
- Optional model selector.
- A list of enabled models.

The frontend must only receive safe model metadata.

Never expose API keys, provider credentials or internal secrets through model configuration endpoints.

## 6.3 Capability-based selection

Future versions should support task-based model selection.

For example:

| Task                  | Desired capability                  |
| --------------------- | ----------------------------------- |
| General chat          | Conversational response             |
| Concept explanation   | Reasoning and instruction following |
| Structured extraction | Structured output                   |
| Research comparison   | Strong reasoning and long context   |
| Simple classification | Low-cost inference                  |

Do not implement complex automatic routing until actual usage and evaluation results justify it.

## 6.4 Model fallback

Provider fallback can be implemented later.

If enabled, it must:

- Use only explicitly configured providers.
- Respect data-sharing and privacy settings.
- Preserve compatible request semantics.
- Record which provider actually served the request.
- Avoid silently sending sensitive data to an unexpected provider.

For the initial release, clear failure reporting is preferable to an uncontrolled fallback system.

---

# 7. AI Tutor Interface

The first visible AI feature should be the Axonweave AI Tutor.

The interface should feel like a professional AI academic assistant.

## 7.1 Main layout

The AI Tutor should contain:

### Left conversation sidebar

- New chat.
- Recent conversations.
- Conversation search.
- Conversation titles.
- Rename conversation.
- Delete conversation.
- Conversation grouping by date, if useful.

### Main chat area

- Welcome screen for a new conversation.
- User messages.
- Assistant messages.
- Streaming responses.
- Code blocks.
- Markdown formatting.
- Copy response.
- Retry response.
- Stop generation.
- Feedback controls.

### Chat input area

- Multiline text input.
- Send button.
- Stop button while generating.
- Enter to send.
- Shift + Enter for a newline.
- Character or token guidance if necessary.
- Model selector, if enabled.

### Header

- AI Tutor title.
- Current conversation title.
- Selected model.
- New conversation action.
- Conversation options.

## 7.2 Welcome screen

When no conversation is selected, display:

**Welcome to Axonweave AI**

"Your personal academic learning companion."

Suggested prompts:

- Explain a difficult concept.
- Teach me a topic step by step.
- Compare two technical concepts.
- Give me an example-based explanation.
- Help me understand a programming problem.

Suggested prompts should populate the input or initiate a real request.

## 7.3 Message display

User messages and assistant messages should have distinct visual styles.

Support:

- Markdown.
- Headings.
- Lists.
- Tables.
- Inline code.
- Fenced code blocks.
- Mathematical notation where supported.
- Links.
- Copy functionality.

Sanitise any untrusted HTML and do not render model-generated HTML as trusted executable content.

## 7.4 Response controls

Provide:

- Copy.
- Regenerate.
- Stop generation.
- Thumbs up.
- Thumbs down.

Feedback should be stored as user feedback, not automatically interpreted as proof of model correctness.

---

# 8. Conversation Management

Conversations must be stored in PostgreSQL.

Do not rely on browser state or localStorage as the source of truth.

## 8.1 Create conversation

When a user starts a new chat:

1. Authenticate the user.
2. Create a conversation record.
3. Associate it with the user.
4. Set its initial title.
5. Return the conversation ID.
6. Open the conversation interface.

Conversation creation should be supported even before the user sends the first message.

## 8.2 Conversation title

Initially, use a simple default title such as:

"New conversation"

After the first user message, the application can generate a short title.

For the initial implementation, a deterministic title based on the first message is acceptable.

Later, an LLM can generate concise titles using a separate low-cost operation.

Do not make title generation necessary for the chat request to succeed.

## 8.3 Conversation operations

Users should be able to:

- Create a conversation.
- List conversations.
- Retrieve a conversation.
- Rename a conversation.
- Archive a conversation.
- Delete a conversation.
- Search conversations.
- Continue an existing conversation.

## 8.4 Conversation ownership

Every conversation must belong to an authenticated user.

Every conversation operation must check ownership.

A user must not be able to retrieve another user's conversation by changing the conversation UUID.

## 8.5 Conversation ordering

Display recent conversations first, using their last activity time.

Use pagination rather than returning an unlimited number of conversations.

---

# 9. Message Management

A conversation contains an ordered sequence of messages.

## 9.1 Message roles

Support these message roles:

- System.
- User.
- Assistant.
- Tool, reserved for future tool execution.

System instructions should not be editable by ordinary users through the conversation interface.

## 9.2 Message lifecycle

A typical request should follow:

```
User submits message
        |
        v
Validate conversation ownership
        |
        v
Save user message
        |
        v
Construct model context
        |
        v
Send request to provider
        |
        v
Receive response
        |
        v
Save assistant response
        |
        v
Update conversation activity
        |
        v
Display completed response
```

For streaming responses, persist the assistant message as an in-progress record or equivalent controlled generation record. Mark it completed, failed or cancelled at the end.

## 9.3 Message statuses

Use statuses such as:

- Pending.
- Streaming.
- Completed.
- Failed.
- Cancelled.

Avoid leaving incomplete assistant messages permanently marked as successful.

## 9.4 Regenerate response

When a user selects regenerate:

- Identify the correct user message.
- Create a new assistant response attempt.
- Preserve the previous response or its history according to the chosen product behaviour.
- Track the new request separately.
- Prevent accidental duplicate generation from repeated clicks.

## 9.5 Stop generation

Support cancellation of an active generation.

The backend should cancel the upstream provider request when the provider supports cancellation.

Mark the corresponding message as cancelled.

Do not charge or report usage inaccurately. Record usage actually reported by the provider where available.

---

# 10. Conversation Context Management

This is a critical part of the AI system.

An LLM API does not automatically know the entire previous conversation unless the application sends relevant history or uses an explicitly supported provider-side conversation mechanism.

Axonweave must implement its own context management.

## 10.1 Context construction

When a user sends a new message:

1. Retrieve the conversation.
2. Verify ownership.
3. Retrieve relevant previous messages.
4. Select the system prompt.
5. Add the current user message.
6. Apply context limits.
7. Send the constructed message sequence to the model.

## 10.2 Context example

```
System instructions
        |
        v
Previous conversation
        |
        v
Current user question
        |
        v
LLM
```

## 10.3 Context window management

Never send unlimited conversation history.

Implement:

- Configurable history limits.
- Input token budgets.
- Maximum output token budgets.
- Message truncation or summarisation policies.
- Protection against exceeding provider context limits.

For the initial implementation:

- Include recent conversation messages.
- Prioritise complete recent turns.
- Exclude old messages when the context budget is exceeded.
- Avoid cutting messages in the middle of important content where possible.

Later, introduce conversation summaries to preserve older context.

## 10.4 Context isolation

Conversation context must remain isolated.

Never include:

- Messages from another user's conversation.
- Unrelated workspace information.
- Private profile data that is not required.
- Hidden system configuration.
- API keys or credentials.

## 10.5 Future academic context

The context manager should eventually support additional context sources:

- Current workspace.
- Current subject.
- Current chapter.
- Uploaded documents.
- User-approved learning preferences.
- Knowledge graph relationships.
- Research project information.

Do not implement all these integrations in Phase 2.

For now, create a clean context-building interface that can accept additional context providers later.

---

# 11. System Prompt Management

System prompts define the assistant's behaviour.

Do not scatter long prompt strings throughout API route handlers.

Create a central prompt management module.

Suggested structure:

```
ai/
|
+-- prompts/
|   |
|   +-- base.py
|   +-- academic_tutor.py
|   +-- general_assistant.py
|   +-- prompt_registry.py
```

## 11.1 Base system prompt

The initial AI Tutor should:

- Act as an academic learning assistant.
- Explain concepts accurately and clearly.
- Adapt explanations to the user's question.
- Use examples where helpful.
- Explain technical concepts step by step.
- Avoid inventing sources or references.
- Distinguish uncertainty from established facts.
- Avoid pretending to have access to uploaded materials when none are available.
- Encourage understanding rather than merely producing answers.

## 11.2 Example system prompt

```
You are Axonweave AI, an academic learning assistant.

Your purpose is to help students, independent learners,
educators and researchers understand academic concepts.

Instructions:

1. Explain concepts clearly and accurately.
2. Adapt the explanation to the user's question.
3. Use examples when they improve understanding.
4. Explain complex concepts step by step.
5. Do not invent citations, research papers or facts.
6. Be transparent about uncertainty.
7. Do not claim to have accessed files or resources
   that were not provided to you.
8. When appropriate, distinguish established facts
   from interpretations and assumptions.
9. Encourage genuine conceptual understanding.
10. Use clear formatting for technical explanations.
```

Treat this as a starting prompt. Evaluate and improve it using actual academic questions.

## 11.3 Prompt versioning

Every system prompt should have:

- Prompt identifier.
- Version.
- Content.
- Active status.
- Created timestamp.
- Updated timestamp.

Store prompt versions in source control or a controlled database table.

Record the prompt version used for each generation.

Do not silently change the system prompt without retaining a version history.

---

# 12. Streaming Responses

Streaming is essential for a modern AI chat experience.

Users should see the response as it is generated rather than waiting for the entire answer.

## 12.1 Recommended approach

Use Server-Sent Events (SSE) for the initial implementation.

The browser sends a request to the backend.

The backend calls the provider's streaming API.

The backend forwards response chunks to the frontend.

## 12.2 Streaming workflow

```
User sends question
        |
        v
Frontend POST request
        |
        v
Backend validates request
        |
        v
Backend starts LLM stream
        |
        v
Provider generates response
        |
        v
Backend receives chunks
        |
        v
Backend sends SSE events
        |
        v
Frontend displays text progressively
        |
        v
Generation completes
        |
        v
Backend saves final message
```

## 12.3 SSE event types

Use a consistent event format.

Suggested events:

- `message.started`
- `message.delta`
- `message.completed`
- `message.failed`
- `message.cancelled`
- `usage.updated`

Example:

```
event: message.started
data: {"message_id":"message-uuid"}

event: message.delta
data: {"delta":"Neural networks are"}

event: message.delta
data: {"delta":" computational models..."}

event: message.completed
data: {"message_id":"message-uuid"}
```

Use appropriate SSE framing and JSON encoding in the actual implementation.

Do not send raw unescaped model content as arbitrary event framing.

## 12.4 Streaming requirements

- Support incremental text updates.
- Handle network disconnections.
- Handle user cancellation.
- Handle provider errors.
- Handle stream completion.
- Persist the final response.
- Avoid duplicate messages.
- Prevent concurrent generation conflicts for the same conversation where appropriate.

## 12.5 Frontend behaviour

While generating:

- Display partial response content.
- Show a loading indicator.
- Disable duplicate send operations as appropriate.
- Display a stop button.
- Allow scrolling through the conversation.
- Preserve completed messages.

If the connection fails, show a clear error and provide a retry option.

---

# 13. Database Architecture

Extend the existing PostgreSQL database.

Do not recreate the Phase 1 database.

Use Alembic migrations.

## 13.1 New database tables

### A. conversations

| Column          | Type      | Purpose                  |
| --------------- | --------- | ------------------------ |
| id              | UUID      | Primary key              |
| user_id         | UUID      | Conversation owner       |
| title           | VARCHAR   | Conversation title       |
| status          | VARCHAR   | Active or archived       |
| model_id        | VARCHAR   | Default model identifier |
| created_at      | TIMESTAMP | Creation time            |
| updated_at      | TIMESTAMP | Last update              |
| last_message_at | TIMESTAMP | Last activity            |

### B. messages

| Column          | Type      | Purpose                         |
| --------------- | --------- | ------------------------------- |
| id              | UUID      | Primary key                     |
| conversation_id | UUID      | Parent conversation             |
| role            | VARCHAR   | User, assistant, system or tool |
| content         | TEXT      | Message content                 |
| status          | VARCHAR   | Generation status               |
| sequence_number | INTEGER   | Message order                   |
| model_id        | VARCHAR   | Model used, where applicable    |
| prompt_version  | VARCHAR   | Prompt version                  |
| input_tokens    | INTEGER   | Input usage                     |
| output_tokens   | INTEGER   | Output usage                    |
| created_at      | TIMESTAMP | Creation time                   |
| completed_at    | TIMESTAMP | Completion time                 |

### C. llm_providers

Stores non-secret provider configuration metadata.

| Column        | Type      | Purpose       |
| ------------- | --------- | ------------- |
| id            | UUID      | Primary key   |
| provider_name | VARCHAR   | Provider      |
| display_name  | VARCHAR   | UI name       |
| is_enabled    | BOOLEAN   | Availability  |
| created_at    | TIMESTAMP | Creation time |
| updated_at    | TIMESTAMP | Update time   |

Do not store plaintext API keys here.

### D. llm_models

| Column            | Type      | Purpose                       |
| ----------------- | --------- | ----------------------------- |
| id                | UUID      | Primary key                   |
| provider_id       | UUID      | Provider reference            |
| internal_model_id | VARCHAR   | Axonweave model identifier |
| provider_model_id | VARCHAR   | Provider model identifier     |
| display_name      | VARCHAR   | UI display name               |
| is_enabled        | BOOLEAN   | Availability                  |
| capabilities      | JSONB     | Supported capabilities        |
| max_input_tokens  | INTEGER   | Verified input limit          |
| max_output_tokens | INTEGER   | Verified output limit         |
| created_at        | TIMESTAMP | Creation time                 |
| updated_at        | TIMESTAMP | Update time                   |

### E. ai_usage_records

| Column          | Type      | Purpose                   |
| --------------- | --------- | ------------------------- |
| id              | UUID      | Primary key               |
| user_id         | UUID      | User                      |
| conversation_id | UUID      | Conversation              |
| message_id      | UUID      | Related assistant message |
| provider_id     | UUID      | Provider                  |
| model_id        | UUID      | Model                     |
| input_tokens    | INTEGER   | Input usage               |
| output_tokens   | INTEGER   | Output usage              |
| estimated_cost  | NUMERIC   | Estimated cost            |
| currency        | VARCHAR   | Currency                  |
| request_status  | VARCHAR   | Success or failure        |
| created_at      | TIMESTAMP | Request timestamp         |

Usage records should distinguish actual provider-reported usage from estimates.

### F. prompt_templates

| Column     | Type      | Purpose           |
| ---------- | --------- | ----------------- |
| id         | UUID      | Primary key       |
| prompt_key | VARCHAR   | Prompt identifier |
| version    | VARCHAR   | Prompt version    |
| content    | TEXT      | Prompt content    |
| is_active  | BOOLEAN   | Active version    |
| created_at | TIMESTAMP | Creation time     |
| updated_at | TIMESTAMP | Update time       |

### G. message_feedback

| Column        | Type      | Purpose              |
| ------------- | --------- | -------------------- |
| id            | UUID      | Primary key          |
| message_id    | UUID      | Assistant message    |
| user_id       | UUID      | Feedback owner       |
| rating        | VARCHAR   | Positive or negative |
| feedback_text | TEXT      | Optional comment     |
| created_at    | TIMESTAMP | Feedback time        |

## 13.2 Database relationships

```
USERS
  |
  +---- CONVERSATIONS
             |
             +---- MESSAGES
             |       |
             |       +---- MESSAGE_FEEDBACK
             |
             +---- AI_USAGE_RECORDS

LLM_PROVIDERS
  |
  +---- LLM_MODELS

PROMPT_TEMPLATES
  |
  +---- REFERENCED BY MESSAGE PROMPT VERSION
```

## 13.3 Database rules

- Use UUIDs.
- Use foreign-key constraints.
- Add indexes on conversation owner and timestamps.
- Add indexes on message conversation ID and sequence number.
- Add uniqueness constraints where required.
- Enforce message ordering.
- Use transactions for related persistence operations.
- Enforce conversation ownership.
- Use UTC timestamps.
- Define retention and deletion policies.

Consider composite foreign-key constraints to ensure that related messages, usage records and feedback cannot be associated with inconsistent owners or conversations.

Do not store provider API keys in these tables.

---

# 14. Backend API Design

Use the existing API versioning:

`/api/v1`

All AI endpoints must require authentication.

## 14.1 Conversation APIs

| Method | Endpoint                       | Purpose               |
| ------ | ------------------------------ | --------------------- |
| POST   | /ai/conversations              | Create conversation   |
| GET    | /ai/conversations              | List conversations    |
| GET    | /ai/conversations/{id}         | Retrieve conversation |
| PATCH  | /ai/conversations/{id}         | Rename or update      |
| DELETE | /ai/conversations/{id}         | Delete conversation   |
| POST   | /ai/conversations/{id}/archive | Archive conversation  |

## 14.2 Message APIs

| Method | Endpoint                                                | Purpose             |
| ------ | ------------------------------------------------------- | ------------------- |
| GET    | /ai/conversations/{id}/messages                         | Retrieve messages   |
| POST   | /ai/conversations/{id}/messages                         | Send message        |
| POST   | /ai/conversations/{id}/messages/{message_id}/regenerate | Regenerate response |
| POST   | /ai/conversations/{id}/messages/{message_id}/cancel     | Cancel generation   |
| POST   | /ai/messages/{message_id}/feedback                      | Submit feedback     |

For streaming, the message endpoint should return a streamed response using SSE.

Ensure the request and response format is documented clearly.

## 14.3 Model APIs

| Method | Endpoint           | Purpose                         |
| ------ | ------------------ | ------------------------------- |
| GET    | /ai/models         | List available models           |
| GET    | /ai/models/default | Retrieve default model          |
| GET    | /ai/capabilities   | Retrieve supported capabilities |

Only expose enabled models and safe configuration metadata.

## 14.4 Usage APIs

| Method | Endpoint           | Purpose                |
| ------ | ------------------ | ---------------------- |
| GET    | /ai/usage          | Current user's usage   |
| GET    | /ai/usage/summary  | Usage summary          |
| GET    | /ai/usage/by-model | Usage grouped by model |

Users must only be able to retrieve their own usage information.

## 14.5 API request example

```
{
  "content": "Explain the working of a convolutional neural network.",
  "model_id": "default",
  "stream": true
}
```

## 14.6 API response example

A non-streaming response could look like:

```
{
  "success": true,
  "data": {
    "conversation_id": "conversation-uuid",
    "message": {
      "id": "message-uuid",
      "role": "assistant",
      "content": "A convolutional neural network...",
      "status": "completed"
    },
    "usage": {
      "input_tokens": 120,
      "output_tokens": 350
    }
  }
}
```

These token counts are illustrative only.

## 14.7 HTTP status codes

Use:

- 200 — Successful retrieval or operation.
- 201 — Resource created.
- 400 — Invalid request.
- 401 — Authentication required.
- 403 — Authenticated but operation not permitted.
- 404 — Resource not found or inaccessible.
- 409 — Conflicting operation.
- 422 — Validation error.
- 429 — Rate limit exceeded.
- 502 — Upstream provider failure.
- 503 — Provider temporarily unavailable.
- 504 — Provider timeout.

Never expose raw provider exceptions to users.

---

# 15. AI Security and Data Protection

LLM integration introduces security risks beyond normal web application security.

Use OWASP guidance for LLM applications and secure API development.

## 15.1 API key protection

Provider API keys must:

- Exist only on the backend.
- Be loaded from environment configuration or a secrets manager.
- Never appear in frontend code.
- Never be returned by API endpoints.
- Never be written to logs.
- Never be committed to Git.

Use separate credentials for development, testing and production.

Apply provider-side spending and rate limits where available.

Rotate credentials when compromised.

## 15.2 Prompt injection protection

Prompt injection occurs when malicious instructions are embedded in user input or external content.

Although document processing is not included yet, the AI system should already be designed with prompt-injection risks in mind.

Implement these principles:

- Treat user messages as untrusted input.
- Keep system instructions separate from user content.
- Never allow user messages to overwrite trusted system instructions.
- Do not reveal hidden system prompts or internal configuration.
- Do not let the LLM independently authorise access to application resources.
- Never trust model-generated resource IDs without backend validation.
- Treat future retrieved documents as untrusted content.
- Clearly separate trusted instructions from reference material.

Prompt instructions alone are not a security boundary. Enforce permissions in application code.

## 15.3 Data isolation

Every conversation and message must belong to an authenticated user.

The backend must enforce:

- Conversation ownership.
- Message ownership through the conversation.
- Feedback ownership.
- Usage record ownership.
- Model access permissions.

Do not trust conversation IDs supplied by the frontend without checking ownership.

## 15.4 Sensitive data handling

Do not automatically send:

- Passwords.
- Session tokens.
- API keys.
- Internal application secrets.
- Unnecessary profile data.
- Other users' messages.
- Unrelated academic content.

Only send the context needed for the request.

## 15.5 External provider privacy

Before sending user data to an external provider, review:

- Provider data-processing terms.
- API data retention.
- Model training policies.
- Regional processing arrangements.
- Applicable contractual commitments.
- Sensitive-data restrictions.

Do not assume consumer chat-product privacy terms are identical to API terms.

Provide a clear privacy explanation to users.

## 15.6 Output safety

Model responses are untrusted generated content.

- Render Markdown safely.
- Escape text.
- Sanitize links and unsafe HTML.
- Do not execute generated JavaScript.
- Do not execute model-generated shell commands.
- Do not execute generated SQL.
- Do not allow the model to perform privileged operations directly.

## 15.7 Abuse prevention

Implement:

- Per-user request limits.
- Per-IP request limits where appropriate.
- Maximum input length.
- Maximum output tokens.
- Maximum active generations per user.
- Provider timeout.
- Concurrency controls.
- Usage quotas.
- Cost controls.

The frontend must not be able to bypass backend quotas by changing its local state.

## 15.8 Prompt and message privacy

Treat stored conversations as private user data.

- Restrict database access.
- Avoid logging complete messages.
- Encrypt storage and backups using infrastructure-supported encryption.
- Establish retention policies.
- Support deletion of conversations.
- Prevent cross-user retrieval.
- Do not use private conversations for model training without appropriate consent and a valid legal basis.

---

# 16. Usage Tracking and Cost Management

This is essential because Axonweave AI will eventually have many AI-powered features.

Every LLM request should be measurable.

## 16.1 What to track

For every request, record:

- User ID.
- Conversation ID.
- Message ID.
- Provider.
- Model.
- Input tokens.
- Output tokens.
- Request status.
- Duration.
- Provider request ID, where available.
- Estimated cost.
- Currency.
- Timestamp.

## 16.2 Token usage

Track:

- Input tokens.
- Output tokens.
- Total tokens.

Use provider-reported usage whenever available.

If streaming responses do not return final usage in the stream, use the provider's documented usage mechanism or a clearly labelled estimate.

Do not treat character counts as exact token counts.

## 16.3 Cost estimation

Maintain a configurable pricing registry.

Illustrative formula:

```
Estimated Cost =
(Input Tokens / 1,000,000 × Input Price)
+
(Output Tokens / 1,000,000 × Output Price)
```

Actual pricing units and model-specific rates must be verified with the provider.

Store pricing metadata with an effective date so historical cost estimates are not silently recalculated using new rates.

## 16.4 Usage dashboard

Display:

- Total requests.
- Total input tokens.
- Total output tokens.
- Estimated usage cost.
- Usage by model.
- Recent requests.
- Failed requests.

For a user-facing application, do not show internal provider secrets or confidential account-level billing details.

## 16.5 Cost controls

Implement:

- Maximum input size.
- Maximum output tokens.
- Per-user usage limits.
- Request rate limits.
- Configurable model allowlists.
- Cost alerts or thresholds.
- Duplicate-request protection.
- Caching only where privacy and correctness permit.

Do not promise that all usage will be free.

The application must be able to operate with no paid API configured, but AI generation will only work when an eligible local model or provider is available.

---

# 17. Error Handling and Reliability

External model APIs can fail.

Axonweave must handle these failures without crashing the application.

## 17.1 Possible failures

- Invalid API key.
- Provider rate limit.
- Insufficient provider quota.
- Network failure.
- Request timeout.
- Provider outage.
- Invalid model identifier.
- Context length exceeded.
- Invalid response.
- Stream interruption.
- Malformed structured output.

## 17.2 Error handling strategy

Create a normalised internal error format.

Example:

```
{
  "success": false,
  "error": {
    "code": "LLM_RATE_LIMITED",
    "message": "The AI service is temporarily busy. Please try again."
  }
}
```

Do not expose raw provider error messages or credentials.

## 17.3 Retry logic

Implement limited retries for transient errors only.

Examples:

- Network interruption.
- Temporary provider outage.
- Retryable server error.

Use exponential backoff with jitter.

Do not repeatedly retry:

- Invalid credentials.
- Invalid model configuration.
- Invalid input.
- Context length errors.

Do not retry a partially completed streaming response blindly. Doing so may create duplicate charges or duplicate messages.

## 17.4 Timeouts

Set separate configurable timeouts for:

- Connection establishment.
- Normal generation.
- Streaming inactivity.
- Overall request duration.

## 17.5 Circuit breaker

A circuit breaker may be introduced when the application needs to prevent repeated calls to an unavailable provider.

For the initial implementation, basic timeouts, retry limits and clear failure handling are sufficient.

---

# 18. AI Evaluation and Quality Testing

A working connection does not automatically mean a useful AI system.

Evaluate answer quality.

## 18.1 Test dataset

Create an internal academic test set containing questions from:

- Computer science.
- Mathematics.
- Artificial intelligence.
- Cloud computing.
- Cybersecurity.
- Database systems.
- Programming.

Include:

- Simple questions.
- Complex explanations.
- Multi-step questions.
- Follow-up questions.
- Ambiguous questions.
- Incorrect assumptions.
- Questions requiring uncertainty.

## 18.2 Evaluation criteria

Evaluate:

| Metric                | Purpose                                       |
| --------------------- | --------------------------------------------- |
| Correctness           | Is the answer factually correct?              |
| Relevance             | Does it answer the actual question?           |
| Clarity               | Is it understandable?                         |
| Instruction following | Does it follow the requested format?          |
| Context retention     | Does it use prior conversation appropriately? |
| Hallucination         | Does it invent unsupported information?       |
| Latency               | How long does generation take?                |
| Cost                  | How expensive is the request?                 |
| Reliability           | Does the request complete successfully?       |

## 18.3 Manual evaluation

Initially, manually review a set of representative responses.

Compare providers only after testing them on the same questions and comparable settings.

Do not select a provider solely based on a few impressive demonstrations.

## 18.4 Automated tests

Automate:

- API response validation.
- Streaming completion.
- Message persistence.
- Context construction.
- Provider failure handling.
- Usage recording.
- Ownership validation.
- Prompt version selection.

Use mocked provider responses for ordinary automated tests so the test suite does not incur API costs.

Maintain a smaller set of optional live-provider tests.

---

# 19. Frontend Project Structure

Extend the existing Next.js project.

Suggested additions:

```
frontend/
|
+-- src/
    |
    +-- app/
    |   +-- (dashboard)/
    |       +-- ai-tutor/
    |           +-- page.tsx
    |           +-- [conversationId]/
    |               +-- page.tsx
    |
    +-- components/
    |   +-- ai/
    |       +-- chat-window.tsx
    |       +-- chat-input.tsx
    |       +-- message-bubble.tsx
    |       +-- streaming-message.tsx
    |       +-- model-selector.tsx
    |       +-- conversation-sidebar.tsx
    |       +-- message-actions.tsx
    |
    +-- features/
    |   +-- ai/
    |       +-- api/
    |       +-- hooks/
    |       +-- types/
    |       +-- utils/
    |
    +-- lib/
        +-- api/
```

## Frontend implementation requirements

- Use typed API responses.
- Use a central API client.
- Include authenticated requests.
- Implement streaming correctly.
- Handle stream cancellation.
- Handle partial failures.
- Preserve conversation history.
- Avoid duplicate message submission.
- Implement responsive chat layout.
- Keep UI state separate from persistent server data.

Use the browser's supported streaming APIs or a compatible SSE client approach.

If authentication uses HTTP-only cookies, configure credentials and CSRF handling correctly for the streaming request.

---

# 20. Backend Project Structure

Extend the existing FastAPI project.

```
backend/
|
+-- app/
    |
    +-- modules/
    |   +-- auth/
    |   +-- users/
    |   +-- workspaces/
    |   +-- subjects/
    |   +-- folders/
    |   +-- chapters/
    |   +-- ai/
    |       |
    |       +-- conversations/
    |       +-- messages/
    |       +-- usage/
    |       +-- models/
    |
    +-- ai/
    |   |
    |   +-- providers/
    |   |   +-- base.py
    |   |   +-- registry.py
    |   |   +-- openai_provider.py
    |   |   +-- gemini_provider.py
    |   |   +-- anthropic_provider.py
    |   |
    |   +-- orchestration/
    |   |   +-- ai_service.py
    |   |   +-- model_router.py
    |   |   +-- context_manager.py
    |   |   +-- response_handler.py
    |   |
    |   +-- prompts/
    |   |   +-- base.py
    |   |   +-- academic_tutor.py
    |   |   +-- prompt_registry.py
    |   |
    |   +-- usage/
    |       +-- token_tracker.py
    |       +-- cost_calculator.py
    |
    +-- models/
    +-- schemas/
    +-- repositories/
    +-- services/
    +-- database/
    +-- core/
    +-- tests/
    +-- main.py
```

The exact folder layout may be adapted to the existing Phase 1 architecture.

Do not duplicate existing authentication, database or configuration modules.

Keep AI-specific code isolated from ordinary application functionality.

---

# 21. Implementation Order

Follow this order carefully.

## Step 1 — Review Phase 1

Before writing code:

- Inspect the existing repository.
- Understand the current backend structure.
- Understand the current frontend structure.
- Inspect the database schema.
- Inspect authentication implementation.
- Inspect API conventions.
- Inspect error handling.
- Inspect existing tests.

Do not recreate the application.

Do not replace working Phase 1 modules without justification.

**Deliverable:** A documented understanding of the current codebase and an integration plan.

## Step 2 — Design the AI architecture

- Define the provider interface.
- Define common request and response schemas.
- Define provider registry.
- Define model configuration.
- Define orchestration service.
- Define error taxonomy.
- Define prompt management.

**Deliverable:** Provider-independent AI architecture.

## Step 3 — Configure the first LLM provider

- Select the first provider.
- Configure credentials.
- Install its SDK.
- Implement provider adapter.
- Implement a normal generation request.
- Validate response parsing.
- Handle errors and timeouts.
- Verify token usage.

**Deliverable:** Axonweave can successfully communicate with the first LLM provider.

## Step 4 — Database implementation

- Create conversations table.
- Create messages table.
- Create provider and model metadata.
- Create usage records.
- Create prompt template records.
- Create feedback records.
- Add migrations.
- Add indexes and constraints.

**Deliverable:** AI data can be persisted reliably.

## Step 5 — Conversation APIs

- Create conversation.
- List conversations.
- Retrieve conversation.
- Rename conversation.
- Delete conversation.
- Archive conversation.
- Implement ownership checks.

**Deliverable:** Persistent conversation management.

## Step 6 — Message and context management

- Save user messages.
- Retrieve conversation history.
- Build context.
- Apply token limits.
- Generate assistant response.
- Save assistant response.
- Update conversation activity.
- Handle failed and cancelled messages.

**Deliverable:** Multi-turn conversations work correctly.

## Step 7 — AI Tutor interface

- Build chat layout.
- Build conversation sidebar.
- Build chat input.
- Build message components.
- Connect backend APIs.
- Add loading states.
- Add empty states.
- Add message actions.
- Add model selector if enabled.

**Deliverable:** A working AI Tutor interface.

## Step 8 — Streaming

- Implement provider streaming.
- Implement backend SSE.
- Implement frontend streaming.
- Implement cancellation.
- Persist final output.
- Handle interrupted streams.

**Deliverable:** Users see responses progressively.

## Step 9 — Usage and cost management

- Extract token usage.
- Record model information.
- Calculate estimated cost.
- Add usage endpoints.
- Add usage summary UI.
- Configure limits.

**Deliverable:** AI consumption is measurable and controllable.

## Step 10 — Security review

- Verify authentication.
- Verify conversation ownership.
- Verify message ownership.
- Protect API keys.
- Add AI-specific rate limits.
- Validate input size.
- Validate output rendering.
- Test cancellation.
- Review logging.
- Review external provider data handling.

**Deliverable:** Secure AI integration.

## Step 11 — Evaluation and final testing

- Test normal conversations.
- Test follow-up questions.
- Test long conversations.
- Test invalid inputs.
- Test provider outages.
- Test streaming failures.
- Test concurrent requests.
- Test usage tracking.
- Test data isolation.
- Review answer quality.

**Deliverable:** Phase 2 passes functional, security and quality tests.

---

# 22. Testing Requirements

## 22.1 Provider tests

- Valid credentials.
- Invalid credentials.
- Normal generation.
- Streaming generation.
- Provider timeout.
- Provider rate limit.
- Invalid model.
- Malformed response.
- Missing usage information.

## 22.2 Conversation tests

- Create conversation.
- List conversations.
- Rename conversation.
- Retrieve conversation.
- Delete conversation.
- Archive conversation.
- Conversation persistence.

## 22.3 Message tests

- Send user message.
- Generate assistant response.
- Persist both messages.
- Maintain ordering.
- Handle failed generation.
- Handle cancelled generation.
- Regenerate response.
- Prevent accidental duplicate submission.

## 22.4 Context tests

- Follow-up questions retain context.
- Unrelated conversations do not leak context.
- Context limits are respected.
- Old messages are handled according to the context policy.
- System instructions remain separate.
- User content cannot override trusted backend instructions.

## 22.5 Security tests

1. User A cannot read User B's conversation.
2. User A cannot send messages to User B's conversation.
3. User A cannot delete User B's conversation.
4. User A cannot access User B's usage records.
5. Unauthenticated users cannot access AI endpoints.
6. Provider credentials are never exposed.
7. Oversized requests are rejected.
8. Rate limits are enforced.
9. Unsafe HTML is not executed.
10. Invalid model IDs are rejected.
11. Failed requests do not produce misleading successful records.
12. Cancelled generations do not continue indefinitely.

## 22.6 Frontend tests

- Chat interface rendering.
- New conversation.
- Conversation selection.
- Message submission.
- Streaming display.
- Stop generation.
- Retry response.
- Copy response.
- Rename conversation.
- Delete conversation.
- Mobile responsiveness.

---

# 23. Phase 2 Acceptance Criteria

Phase 2 is complete only when these requirements are satisfied.

## LLM integration

- At least one provider is successfully integrated.
- API keys are securely configured.
- Model configuration is centralised.
- Provider-specific code is isolated.
- Normal text generation works.
- Provider errors are handled.
- Timeouts are configured.

## AI Tutor

- User can start a conversation.
- User can submit a question.
- Assistant can respond.
- Streaming works.
- Follow-up questions retain context.
- Conversation history is persisted.
- User can switch between conversations.
- User can rename conversations.
- User can delete conversations.
- User can stop generation.

## Context and prompts

- System prompt is centrally managed.
- Prompt version is recorded.
- Conversation history is included appropriately.
- Context limits are enforced.
- Conversations remain isolated.
- No unsupported file or academic context is invented.

## Usage

- Input tokens are recorded where available.
- Output tokens are recorded where available.
- Model usage is recorded.
- Estimated costs are calculated when pricing data is available.
- Users can view their own usage.
- Configurable request limits are enforced.

## Security

- Provider keys remain on the backend.
- AI endpoints require authentication.
- Conversation ownership is verified.
- User data is isolated.
- Input limits are implemented.
- Rate limiting works.
- Generated content is rendered safely.
- Sensitive content is excluded from logs.

## Quality

- Tests pass.
- AI responses are evaluated.
- Provider failures do not crash the application.
- Database persistence works.
- Documentation is updated.

---

# 24. Features Outside Phase 2

Do not implement these yet:

- PDF parsing.
- PPTX parsing.
- DOCX parsing.
- OCR.
- Document chunking.
- Embedding generation.
- Vector database.
- RAG.
- Citation-grounded document answers.
- Flashcard generation.
- Quiz generation.
- Spaced repetition.
- Knowledge graph.
- Learner intelligence.
- Research-paper extraction.
- Research comparison.
- Audio generation.
- Speech recognition.
- AI agents.
- Complex tool execution.
- Multi-agent orchestration.

These will be implemented in their respective future phases.

The AI architecture must be extensible enough to support them without replacing the core provider and orchestration systems.

---

# 25. Documentation Requirements

Update the project documentation.

Create:

- `docs/AI_ARCHITECTURE.md`
- `docs/LLM_PROVIDER_INTEGRATION.md`
- `docs/AI_API_REFERENCE.md`
- `docs/CONVERSATION_MANAGEMENT.md`
- `docs/AI_SECURITY.md`
- `docs/USAGE_AND_COST_TRACKING.md`
- `docs/AI_TESTING.md`

The documentation must explain:

- How providers are configured.
- How to add a new provider.
- How model selection works.
- How conversations are stored.
- How context is constructed.
- How streaming works.
- How usage is tracked.
- How security is enforced.
- How to run tests.

Never place actual API credentials in documentation.

---

# 26. Final Development Instructions

Build Phase 2 on top of the existing Axonweave AI codebase.

Do not rebuild Phase 1.

Do not replace working authentication or database infrastructure.

Follow the provider-independent architecture.

Use one LLM provider initially, but keep the system extensible.

Do not expose API keys to the frontend.

Do not allow the LLM to control database access or application permissions directly.

Do not treat model output as trusted content.

Do not implement RAG or document intelligence prematurely.

Do not hardcode responses or use fake AI output.

Do not create buttons that do not perform real operations.

Do not leave security requirements as TODO comments.

For every feature:

1. Inspect the existing implementation.
2. Design the required changes.
3. Update database models where needed.
4. Create Alembic migrations.
5. Implement backend schemas.
6. Implement repository and service logic.
7. Implement API routes.
8. Add authentication and authorization.
9. Write tests.
10. Build frontend components.
11. Integrate frontend and backend.
12. Test the complete workflow.
13. Update documentation.

Implement incrementally and verify every milestone before moving forward.

**Final outcome:** Axonweave AI will have a functioning, provider-independent AI foundation with an integrated LLM, persistent AI Tutor, multi-turn conversations, streaming responses, central prompt management, context handling, usage monitoring, cost controls and AI-specific security.

This will serve as the common intelligence infrastructure for the upcoming document intelligence, learning and research modules.

## How I recommend you execute Phase 2

Work through the milestones in order.

## Phase 2 development milestones

1. Review Phase 1 codebase

   Inspect the existing project, database, authentication and API conventions.
2. Build the provider abstraction

   Define interfaces, schemas and provider registry.
3. Connect the first LLM

   Test a real API request from the backend.
4. Implement conversations and messages

   Add persistent storage and context management.
5. Build the AI Tutor UI

   Connect the chat interface to the backend.
6. Implement streaming

   Add SSE, cancellation and message persistence.
7. Implement usage and security

   Add token tracking, cost estimation, quotas and testing.

## Three decisions before implementation

These are the only things I would settle before starting the actual coding.

1\. Initial LLM provider: I recommend benchmarking OpenAI and Gemini first, then choosing one primary provider. We should verify their current model availability and pricing before committing.

2\. API spending: Start with a strict development budget and request limits. A small number of real API requests is enough to develop and test the integration.

3\. Existing codebase: Extend Phase 1 rather than starting a new project. Database migrations must preserve existing users, workspaces and academic data.

