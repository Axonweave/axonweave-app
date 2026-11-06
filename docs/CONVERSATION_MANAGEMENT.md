# Conversation management

How AI Tutor conversations and messages are stored, ordered, titled, cancelled and recovered, and how
context is built. Code: `backend/app/modules/ai/`, `backend/app/ai/orchestration/`,
`backend/app/repositories/ai_*_repository.py`. Tables are described in `docs/AI_ARCHITECTURE.md` section 8.

## Storage and ownership

- A **conversation** belongs to one user (`conversations.user_id`). A **message** repeats `user_id` and has a composite
  foreign key `(conversation_id, user_id)` to the conversation, so the database itself refuses a message attached to
  someone else's conversation. Feedback and usage records use the same composite-key approach.
- Every repository method takes `user_id`; there is no query by id alone. A missing conversation and another user's
  conversation give the same 404 (D-56), so existence is not leaked.
- The system prompt is **not** a message row (D-41). Each assistant message stores `prompt_key` and `prompt_version`.

## Lifecycle

| Action | Behaviour |
|---|---|
| Create | Works before any message. Optional title and model. The model id must be an enabled model. |
| Title | From the first message: first ~60 characters, whitespace collapsed, no LLM call (D-55). A title the user set is never overwritten. Rename accepts 1 to 200 non-blank characters. |
| List | Newest activity first (`last_message_at`), paginated, filter by status, title search with wildcards escaped. Archived conversations are hidden by default. |
| Archive | The conversation becomes read-only: sending returns 409 `CONVERSATION_ARCHIVED`. The UI can archive but has no "archived chats" view yet. |
| Delete | Hard-deletes the conversation, its messages and feedback. Usage records stay, with their conversation and message links set to null (so the history of consumption survives without content). |
| Account deletion / export | Removes or includes the user's own AI data only (D-53). |

## Messages

Sequence numbers are assigned in the transaction that locks the conversation row (`COALESCE(MAX)+1`), with
`UNIQUE (conversation_id, sequence_number)` as the backstop, so ordering is stable under concurrency (D-42).

Statuses: `pending` (assistant row created), `streaming`, `completed`, `failed`, `cancelled`. Sending a message stores the user
message and a `pending` assistant message in one transaction, then generates.

**One active generation per conversation** is enforced by a partial unique index on assistant rows in `pending`/`streaming` (D-43):
a second concurrent send gets 409 `AI_GENERATION_IN_PROGRESS` and leaves no rows. Per user, at most `AI_MAX_ACTIVE_GENERATIONS_PER_USER`
(default 2) run at once; more gives 429 `AI_QUOTA_EXCEEDED`. The UI also ignores Enter and the Send button while a response is generating.

**Regenerate** is allowed for the latest answer only. The old answer stays, gets `superseded_at`, and is excluded from future context.
Repeated clicks produce one new attempt.

**Failed or cancelled** answers keep their partial text and status. They are not sent back to the model as context, and the conversation is usable again
immediately.

## Context construction (D-47, D-48)

For each request the context manager (`ai/orchestration/context.py`) builds, from this conversation only:

1. the system prompt (always included, always in the provider's system slot);
2. recent history, limited to `LLM_HISTORY_LIMIT` messages (default 20), excluding superseded, failed and cancelled answers and the pending row;
3. the new user message (always included).

History is added as whole turns from newest to oldest while a token budget holds (model input limit minus reserved output). A turn is dropped whole, never cut.
If the system prompt plus the new message alone exceed the budget the request fails cleanly with 422 `LLM_CONTEXT_TOO_LONG`. Tokens are counted with the
provider's counter when available, otherwise estimated conservatively. Nothing else is sent: no profile data, no other conversations, no files. The result is logged
as counts only (`ai_context_built`), never as text.

Tests: follow-ups keep earlier turns in order; unrelated conversations do not leak; the history limit and token budget drop the oldest whole turns; the system prompt is separate
from user text; a 60-turn conversation still works with a bounded context (`tests/ai/test_ai_messages.py`, `tests/ai/test_ai_closeout.py`).

## Cancellation and recovery

- **Stop button:** `POST .../messages/{id}/cancel` cancels the upstream call, keeps partial text, sets `cancelled`, and records usage (real figures if the provider had
  reported any, otherwise unknown). A closed browser tab or lost connection does the same.
- **Registry limit (D-45):** the cancel endpoint finds the generation in an in-process registry, so it works on the instance running it. A disconnect cancels on any instance.
- **Stuck generations (D-46):** a crash or restart can leave a row `pending`/`streaming`. A sweeper at startup and every 60 s marks rows older than `AI_STALE_GENERATION_SECONDS`
  (default 300) as `failed` and writes a failed usage record. It never touches a generation this process is still running, and uses compare-and-set so a slow one is safe.

## Not covered / limits

No conversation search by message content, no sharing, no export of a single conversation, no archived-chats screen, and the UI loads messages in pages of 100
(longer conversations are not stress-tested). Streaming and cancel behind buffering proxies are unverified.
