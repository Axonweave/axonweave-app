# Axonweave
## Phase 1 — Application Foundation: Complete Development Specification

**Project:** Axonweave  
**Phase:** 1 — Application Foundation  
**Application type:** Responsive full-stack web application  
**Primary objective:** Establish a secure, scalable and maintainable foundation for the complete Axonweave platform.

---

# 1. Project Overview

## 1.1 Product vision

Axonweave is a personal academic intelligence workspace designed to help students, independent learners, educators and researchers organise academic materials, understand concepts, retain knowledge, evaluate their learning and conduct research.

The platform will eventually include:

- AI-powered academic tutoring.
- Document intelligence and RAG.
- Summaries, flashcards and quizzes.
- Adaptive learning and spaced repetition.
- Academic knowledge graphs.
- Research-paper analysis.
- Research assistance and writing tools.
- Audio-based learning.
- Academic collaboration.

Phase 1 must establish the application infrastructure on which all these capabilities can be built.

## 1.2 Phase 1 objective

Develop a functional web application with:

1. User registration and authentication.
2. Secure login and logout.
3. User dashboard.
4. Main sidebar navigation.
5. User profile and account settings.
6. Workspace creation and management.
7. Subject management.
8. Folder management.
9. Chapter management.
10. Database architecture.
11. Backend APIs.
12. Secure access control.
13. Data validation and protection.
14. Error handling and application logging.
15. Responsive design.

The application must support multiple users, with each user's academic data securely isolated from other users.

## 1.3 Development principles

- Security must be implemented from the beginning.
- Use a modular architecture.
- Keep frontend and backend responsibilities separate.
- Use a relational database for structured academic data.
- Follow REST API conventions.
- Implement authentication and authorization independently of frontend visibility.
- Avoid hardcoding credentials and secrets.
- Keep the architecture independent of any particular LLM provider.
- Design the database to support future AI, document and research features.
- Prefer working, tested functionality over decorative UI elements.

---

# 2. Technology Stack

Use the following technology stack for Phase 1.

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js | Web application framework |
| UI library | React | Component-based interface |
| Language | TypeScript | Type safety |
| Styling | Tailwind CSS | Responsive styling |
| UI components | shadcn/ui | Reusable interface components |
| Backend | Python + FastAPI | REST APIs and business logic |
| Database | PostgreSQL | Persistent application data |
| ORM | SQLAlchemy | Database interaction |
| Migrations | Alembic | Database schema versioning |
| Validation | Pydantic | Request and response validation |
| Authentication | Secure server-managed sessions | User authentication |
| Password hashing | Argon2id | Secure password storage |
| Cache (later) | Redis | Caching and background coordination |
| API documentation | OpenAPI / Swagger | API documentation |
| Testing | Pytest + Playwright | Backend and frontend testing |
| Containerisation | Docker | Consistent development environment |
| Version control | Git + GitHub | Source control |

### Architecture decision

Use a modular monolith.

Do not introduce microservices, Kubernetes, multiple databases or complicated distributed infrastructure during Phase 1.

The application should initially consist of:

- One Next.js frontend.
- One FastAPI backend.
- One PostgreSQL database.
- One migration system.
- One Docker-based development environment.

This is sufficient for the initial product and can evolve as the application grows.

---

# 3. System Architecture

The application must follow a clear separation of responsibilities.

## 3.1 High-level architecture

```text
                    USER
                     |
                     v
             NEXT.JS FRONTEND
                     |
             HTTPS / API REQUESTS
                     |
                     v
               FASTAPI BACKEND
                     |
        +------------+-------------+
        |            |             |
        v            v             v
   Authentication  Workspace    User/Profile
     Module         Module        Module
        |            |             |
        +------------+-------------+
                     |
                     v
                SQLAlchemy
                     |
                     v
                POSTGRESQL
```

## 3.2 Frontend responsibilities

The frontend must handle:

- User interface rendering.
- Navigation.
- Forms and user input.
- Client-side field validation for usability.
- Displaying API responses.
- Loading and error states.
- Session-aware interface rendering.
- Responsive layouts.

The frontend must never be trusted to enforce security.

Hiding a button or restricting a page in React is not sufficient authorization. The backend must independently verify every protected operation.

## 3.3 Backend responsibilities

The backend must handle:

- Authentication.
- Authorization.
- User identity verification.
- Workspace ownership.
- Academic data management.
- Request validation.
- Database transactions.
- Business rules.
- Error handling.
- Security checks.
- API responses.

## 3.4 Database responsibilities

PostgreSQL will store:

- User accounts.
- User profiles.
- Workspaces.
- Subjects.
- Folders.
- Chapters.
- User preferences.
- Session information, if server-side sessions are persisted in the database.

Do not store passwords in plain text.

Do not store API keys, access tokens or other credentials in ordinary database fields.

---

# 4. Application Structure and Navigation

The application should have a clean, professional academic workspace interface.

## 4.1 Main application layout

After authentication, users should enter the main Axonweave dashboard.

The layout should contain:

### A. Left sidebar

The sidebar should provide the primary navigation.

**Main navigation:**

- Overview
- My Workspace
- Subjects
- Library
- AI Tutor — coming soon
- Research Studio — coming soon
- Assessments — coming soon
- Revision — coming soon

**Personal section:**

- Recent activity
- Favourites
- Archived items

**Bottom section:**

- Settings
- Help and support
- User profile
- Logout

Future modules can be displayed as disabled or clearly marked as coming soon. Do not make unfinished navigation items appear functional.

### B. Main content area

The main area changes based on the selected navigation item.

Examples:

- Dashboard: overview and recent activity.
- Workspace: workspace list and workspace details.
- Subjects: subjects belonging to the selected workspace.
- Settings: user preferences and account configuration.

### C. Header

Include:

- Current page title.
- Breadcrumb navigation.
- Workspace selector, where appropriate.
- User profile menu.
- Notifications icon, initially with a placeholder or basic implementation.

### D. Responsive behaviour

Desktop:
- Persistent collapsible sidebar.
- Main content uses available width.
- Comfortable spacing and readable typography.

Tablet:
- Collapsible navigation.
- Adaptive content grids.

Mobile:
- Sidebar becomes a drawer.
- Touch-friendly controls.
- Forms and cards adapt to narrow screens.
- No horizontal overflow.

---

# 5. Authentication and Account Management

Authentication is one of the most important parts of Phase 1.

Implement it securely rather than building a custom authentication mechanism from scratch.

## 5.1 Registration

Create a registration page with:

- Full name.
- Email address.
- Password.
- Confirm password.
- Terms and privacy acknowledgement.
- Register button.
- Link to the login page.

### Registration requirements

1. Validate all required fields.
2. Validate email format.
3. Normalise email addresses before uniqueness checks.
4. Enforce password length and strength requirements.
5. Check whether the email is already registered.
6. Hash the password using Argon2id.
7. Create the user account.
8. Create the associated profile.
9. Create an initial personal workspace, if that is the selected onboarding experience.
10. Return a safe response without exposing internal account details.

Do not return password hashes in API responses.

### Password policy

Use a modern password policy:

- Require a minimum length of at least 12 characters.
- Permit long passphrases.
- Support password managers and paste functionality.
- Do not impose arbitrary mandatory mixtures of uppercase, lowercase, digits and symbols.
- Check passwords against known compromised-password lists where practical.
- Do not store or log submitted passwords.

Use Argon2id with parameters selected and benchmarked for the deployment environment.

## 5.2 Login

Login page fields:

- Email address.
- Password.
- Remember-me option, if supported by the session design.
- Login button.
- Forgot password link.
- Registration link.

### Login workflow

```text
User enters credentials
          |
          v
Frontend sends login request
          |
          v
Backend validates request
          |
          v
Backend retrieves account
          |
          v
Verify password hash
          |
          v
Check account status
          |
          v
Create authenticated session
          |
          v
Set secure session cookie
          |
          v
Return safe user information
```

If authentication fails, use a generic error such as:

"Invalid email or password."

Do not reveal whether an email address exists.

## 5.3 Session management

For this application, prefer secure, server-managed sessions using opaque session identifiers.

Recommended implementation:

- Generate cryptographically secure random session IDs.
- Store only a hash of the session identifier server-side.
- Send the session identifier through an HTTP-only cookie.
- Use `Secure` cookies in production.
- Set `SameSite=Lax` or a stricter setting where compatible.
- Use an appropriate cookie path and domain.
- Set session expiration.
- Rotate session identifiers after authentication and privilege changes.
- Invalidate sessions on logout.
- Support revoking all sessions after password changes or suspected account compromise.

Do not store long-lived authentication tokens in browser localStorage.

If a JWT-based architecture is selected later, it must include proper expiration, refresh-token rotation, revocation and secure storage. Do not mix session and JWT approaches without a clear reason.

## 5.4 Logout

When a user logs out:

1. Invalidate the server-side session.
2. Expire the authentication cookie.
3. Clear relevant client-side user state.
4. Redirect to the login page.

The user must not be able to access protected pages after logout simply by using the browser's back button.

## 5.5 Forgot password

Implement a secure password-reset workflow.

1. User enters their email.
2. Backend returns a generic confirmation message.
3. If the account exists, generate a cryptographically random, single-use reset token.
4. Store only a hash of the token.
5. Set a short expiration period.
6. Send a reset link through an email provider.
7. Validate the token when the user opens the link.
8. Allow the user to create a new password.
9. Invalidate the reset token.
10. Revoke existing sessions after successful reset.

Do not expose reset tokens through application logs or analytics.

Password-reset links must use a trusted, configured application origin rather than an arbitrary Host header.

## 5.6 Email verification

Support email verification.

A new account should have an email verification status.

Recommended account states:

- Pending verification.
- Active.
- Suspended.
- Deactivated.

The system should enforce the chosen verification policy on protected account operations.

Use expiring, single-use verification tokens.

## 5.7 Authentication security

Implement:

- Rate limiting on registration, login and password-reset endpoints.
- Protection against brute-force attempts.
- Generic authentication errors.
- Session expiration.
- Secure cookies.
- CSRF protection for cookie-authenticated state-changing requests.
- Email verification.
- Secure password hashing.
- Account status checks.
- Security event logging.

Consider progressive delays and temporary rate limits rather than permanent account lockouts that attackers could abuse to deny service.

---

# 6. User Profile and Settings

Each user should have a profile that stores personal application preferences.

## 6.1 Profile page

Display:

- Profile picture or avatar.
- Full name.
- Email address.
- Account creation date.
- Account verification status.
- Preferred language.
- Time zone.

Allow users to edit permitted fields.

## 6.2 Settings page

Create the following settings sections.

### Account settings

- Change full name.
- Change email address.
- Change password.
- Manage active sessions.
- Delete account.

Changing an email address should require verification of the new address.

### Appearance

- Light mode.
- Dark mode.
- System theme.

### Learning preferences

Reserve fields for future functionality:

- Preferred explanation style.
- Preferred language.
- Academic level.
- Study preferences.

Do not build complex adaptive learning logic during Phase 1.

### Privacy settings

- Download personal data.
- Request account deletion.
- Manage consent.
- View privacy policy.

Implement the actual export and deletion workflows before presenting these controls as functional.

---

# 7. Workspace Management

A workspace is the main container for a user's academic activities.

A user should be able to organise different areas of learning independently.

Example:

```text
Axonweave
|
+-- Workspace: University
|   |
|   +-- Machine Learning
|   |   |
|   |   +-- Neural Networks
|   |   +-- CNN
|   |   +-- Transformers
|   |
|   +-- Cloud Computing
|       |
|       +-- Cloud Architecture
|       +-- Cloud Security
|
+-- Workspace: Personal Learning
    |
    +-- Cybersecurity
    +-- Java Development
```

## 7.1 Workspace creation

Workspace creation form:

- Workspace name.
- Description.
- Workspace type.
- Optional colour or icon.

Suggested workspace types:

- University.
- Personal learning.
- Research.
- Professional development.
- Custom.

## 7.2 Workspace operations

Users must be able to:

- Create workspace.
- View workspaces.
- Edit workspace details.
- Set a default workspace.
- Archive workspace.
- Restore archived workspace.
- Delete workspace.

Deletion should use a clearly defined policy.

For the initial implementation, use soft deletion or an archive workflow where appropriate, followed by an explicit permanent deletion process.

## 7.3 Workspace ownership

Every workspace must belong to an authenticated user.

The backend must check ownership before allowing any operation on a workspace.

A user must never be able to access another user's workspace by changing a URL or API identifier.

---

# 8. Subject Management

Subjects represent major academic areas within a workspace.

Examples:

- Artificial Intelligence.
- Machine Learning.
- Cloud Computing.
- Database Management Systems.
- Cybersecurity.

## 8.1 Subject creation

Fields:

- Subject name.
- Description.
- Workspace.
- Subject colour.
- Optional icon.

## 8.2 Subject operations

- Create subject.
- View subject.
- Edit subject.
- Archive subject.
- Restore subject.
- Delete subject.
- Search subjects.
- Filter by workspace.
- Sort by name or recently updated.

## 8.3 Subject details page

The page should display:

- Subject title.
- Description.
- Associated workspace.
- Total folders.
- Total chapters.
- Recent activity.
- Folder and chapter hierarchy.

Reserve areas for future AI-generated summaries and learning progress, but do not show fabricated statistics.

---

# 9. Folder Management

Folders organise chapters and other academic resources within a subject.

Example:

```text
Machine Learning
|
+-- Unit 1
|   +-- Introduction
|   +-- Types of Learning
|
+-- Unit 2
|   +-- Neural Networks
|   +-- Backpropagation
|
+-- Unit 3
    +-- CNN
    +-- RNN
```

## 9.1 Folder operations

- Create folder.
- Rename folder.
- Edit description.
- Move folder, subject to hierarchy rules.
- Archive folder.
- Delete folder.
- List folder contents.

For Phase 1, allow a simple hierarchy. Avoid unlimited recursive folder nesting until it is genuinely required.

Validate that folders cannot be moved into themselves or their descendants.

---

# 10. Chapter Management

Chapters represent individual academic topics within a subject or folder.

## 10.1 Chapter creation

Fields:

- Chapter title.
- Description.
- Parent subject.
- Optional folder.
- Display order.
- Status.

Suggested statuses:

- Not started.
- In progress.
- Completed.

These are organisational statuses only. Do not equate them with verified learner mastery.

## 10.2 Chapter operations

- Create chapter.
- View chapter.
- Edit chapter.
- Reorder chapters.
- Move chapter.
- Archive chapter.
- Delete chapter.
- Search chapters.

## 10.3 Chapter detail page

Display:

- Chapter title.
- Subject and workspace breadcrumb.
- Description.
- Folder location.
- Creation date.
- Last updated date.
- Organisational status.

Reserve tabs for future capabilities:

- Learning materials.
- AI explanations.
- Flashcards.
- Quizzes.
- Notes.
- Revision history.

For Phase 1, these may be marked as coming soon.

---

# 11. Dashboard

The dashboard is the user's starting point after login.

It should feel like a personal academic workspace rather than a generic administration panel.

## 11.1 Dashboard components

### Welcome section

Display:

"Welcome back, [User Name]"

Provide a short contextual introduction.

### Quick actions

- Create workspace.
- Create subject.
- Create folder.
- Create chapter.

### Workspace overview

Display workspace cards containing:

- Workspace name.
- Description.
- Number of subjects.
- Last updated date.

### Recent activity

Initially track real actions such as:

- Created workspace.
- Created subject.
- Updated chapter.
- Archived folder.

### Recent subjects

Display recently accessed or updated subjects.

### Quick navigation

Provide easy access to the user's main academic areas.

## 11.2 Dashboard rules

- Only display information belonging to the authenticated user.
- Fetch actual data from backend APIs.
- Do not hardcode demonstration statistics in production.
- Include loading, empty and error states.
- Do not generate fake recent activity.

---

# 12. Database Architecture

Use PostgreSQL as the primary relational database.

Use SQLAlchemy for database access and Alembic for migrations.

## 12.1 Core database tables

### A. users

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| email | VARCHAR | Unique login email |
| password_hash | TEXT | Argon2id hash |
| is_verified | BOOLEAN | Email verification |
| status | VARCHAR | Account status |
| created_at | TIMESTAMP | Account creation |
| updated_at | TIMESTAMP | Last update |

### B. user_profiles

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Foreign key |
| full_name | VARCHAR | User name |
| avatar_url | TEXT | Profile image reference |
| preferred_language | VARCHAR | Language |
| timezone | VARCHAR | User time zone |
| created_at | TIMESTAMP | Creation date |
| updated_at | TIMESTAMP | Last update |

### C. workspaces

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Owner |
| name | VARCHAR | Workspace name |
| description | TEXT | Description |
| workspace_type | VARCHAR | Workspace category |
| icon | VARCHAR | Optional icon |
| is_default | BOOLEAN | Default workspace |
| created_at | TIMESTAMP | Creation date |
| updated_at | TIMESTAMP | Last update |
| archived_at | TIMESTAMP | Archive timestamp |

### D. subjects

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Parent workspace |
| name | VARCHAR | Subject name |
| description | TEXT | Description |
| colour | VARCHAR | UI colour |
| icon | VARCHAR | Optional icon |
| created_at | TIMESTAMP | Creation date |
| updated_at | TIMESTAMP | Last update |
| archived_at | TIMESTAMP | Archive timestamp |

### E. folders

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| subject_id | UUID | Parent subject |
| parent_folder_id | UUID | Optional parent folder |
| name | VARCHAR | Folder name |
| description | TEXT | Description |
| display_order | INTEGER | Sorting |
| created_at | TIMESTAMP | Creation date |
| updated_at | TIMESTAMP | Last update |
| archived_at | TIMESTAMP | Archive timestamp |

### F. chapters

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| subject_id | UUID | Parent subject |
| folder_id | UUID | Optional folder |
| title | VARCHAR | Chapter title |
| description | TEXT | Description |
| display_order | INTEGER | Sorting |
| status | VARCHAR | Organisational status |
| created_at | TIMESTAMP | Creation date |
| updated_at | TIMESTAMP | Last update |
| archived_at | TIMESTAMP | Archive timestamp |

### G. sessions

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Account owner |
| session_token_hash | TEXT | Hashed session identifier |
| expires_at | TIMESTAMP | Expiration |
| created_at | TIMESTAMP | Creation date |
| last_used_at | TIMESTAMP | Last activity |

### H. password_reset_tokens

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Account owner |
| token_hash | TEXT | Hashed reset token |
| expires_at | TIMESTAMP | Expiration |
| used_at | TIMESTAMP | Single-use tracking |
| created_at | TIMESTAMP | Creation date |

### I. activity_logs

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Account owner |
| action | VARCHAR | Activity type |
| entity_type | VARCHAR | Workspace, subject, folder or chapter |
| entity_id | UUID | Related entity |
| created_at | TIMESTAMP | Activity timestamp |

Activity logs should contain only the information required for product functionality. Security audit events should be managed separately with suitable retention and access controls.

## 12.2 Database relationships

```text
USERS
  |
  +---- USER_PROFILES
  |
  +---- WORKSPACES
             |
             +---- SUBJECTS
                       |
                       +---- FOLDERS
                       |       |
                       |       +---- FOLDERS (parent-child)
                       |
                       +---- CHAPTERS

USERS
  |
  +---- SESSIONS
  |
  +---- PASSWORD_RESET_TOKENS
  |
  +---- ACTIVITY_LOGS
```

## 12.3 Database rules

- Use UUID primary keys.
- Use foreign-key constraints.
- Add appropriate indexes.
- Add unique constraints where required.
- Use UTC timestamps in storage.
- Store time zones as IANA identifiers.
- Use transactions for multi-step database operations.
- Use migrations rather than manually changing production schemas.
- Define deletion and archival behaviour explicitly.
- Validate that every nested resource belongs to the correct user's workspace.

Important: a chapter's `subject_id` and `folder_id` must be consistent. A chapter must not reference a folder belonging to a different subject.

For stronger database-level tenant isolation, evaluate PostgreSQL Row-Level Security. If enabled, establish the authenticated user context safely for every database transaction and ensure connection-pool state is reset between requests. Application-level ownership checks remain mandatory.

---

# 13. Backend API Design

Use REST APIs with consistent request and response formats.

Base path:

`/api/v1`

All protected endpoints must require authentication and verify ownership.

## 13.1 Authentication endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /auth/register | Register user |
| POST | /auth/login | Login |
| POST | /auth/logout | Logout |
| GET | /auth/me | Current authenticated user |
| POST | /auth/forgot-password | Request reset |
| POST | /auth/reset-password | Reset password |
| POST | /auth/verify-email | Verify email |
| POST | /auth/resend-verification | Resend verification |

## 13.2 Profile endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /users/me | Get profile |
| PATCH | /users/me | Update profile |
| PATCH | /users/me/password | Change password |
| GET | /users/me/sessions | List sessions |
| DELETE | /users/me/sessions/{id} | Revoke session |
| DELETE | /users/me | Request account deletion |

## 13.3 Workspace endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /workspaces | Create workspace |
| GET | /workspaces | List workspaces |
| GET | /workspaces/{id} | Get workspace |
| PATCH | /workspaces/{id} | Update workspace |
| DELETE | /workspaces/{id} | Delete workspace |
| POST | /workspaces/{id}/archive | Archive workspace |
| POST | /workspaces/{id}/restore | Restore workspace |

## 13.4 Subject endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /workspaces/{id}/subjects | Create subject |
| GET | /workspaces/{id}/subjects | List subjects |
| GET | /subjects/{id} | Get subject |
| PATCH | /subjects/{id} | Update subject |
| DELETE | /subjects/{id} | Delete subject |

## 13.5 Folder endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /subjects/{id}/folders | Create folder |
| GET | /subjects/{id}/folders | List folders |
| GET | /folders/{id} | Get folder |
| PATCH | /folders/{id} | Update folder |
| DELETE | /folders/{id} | Delete folder |
| POST | /folders/{id}/move | Move folder |

## 13.6 Chapter endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /subjects/{id}/chapters | Create chapter |
| GET | /subjects/{id}/chapters | List chapters |
| GET | /chapters/{id} | Get chapter |
| PATCH | /chapters/{id} | Update chapter |
| DELETE | /chapters/{id} | Delete chapter |
| POST | /chapters/{id}/move | Move chapter |
| POST | /chapters/reorder | Reorder chapters |

## 13.7 Dashboard endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /dashboard/overview | Dashboard statistics |
| GET | /dashboard/recent-activity | Recent user activity |
| GET | /dashboard/recent-subjects | Recent subjects |

## 13.8 API standards

Every API must have:

- Request validation.
- Response schemas.
- Authentication checks.
- Authorization checks.
- Consistent HTTP status codes.
- Consistent error responses.
- Pagination for list endpoints where appropriate.
- Sorting and filtering where appropriate.
- API documentation.

Example response:

```json
{
  "success": true,
  "data": {
    "id": "workspace-uuid",
    "name": "University",
    "description": "Academic workspace"
  }
}
```

Example error:

```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found."
  }
}
```

Do not expose stack traces, database errors, SQL queries, internal file paths or sensitive account information in production API responses.

---

# 14. Security and Data Protection Requirements

Security must be treated as a core architectural requirement.

Use OWASP ASVS as a security verification baseline, alongside the OWASP API Security Top 10 and relevant OWASP Cheat Sheets.

## 14.1 Authentication security

Implement:

- Argon2id password hashing.
- Secure, server-managed sessions.
- HTTP-only cookies.
- Secure cookie flag in production.
- Appropriate SameSite policy.
- Session expiration and revocation.
- CSRF protection.
- Login rate limiting.
- Password-reset token hashing and expiration.
- Email verification.
- Generic login and recovery responses.
- Re-authentication for sensitive account changes.

## 14.2 Authorization security

Use deny-by-default authorization.

Every resource access must verify:

1. User is authenticated.
2. User account is active.
3. Resource exists.
4. Resource belongs to the authenticated user.
5. Related parent resources also belong to that user.
6. The requested operation is permitted.

Example:

If user A creates a workspace, user B must not be able to access it by guessing or obtaining its UUID.

Never rely on unpredictable UUIDs as a substitute for authorization.

Prevent insecure direct object reference vulnerabilities (IDOR/BOLA).

## 14.3 Input validation

Validate all data on the backend.

Examples:

- Email format.
- Name length.
- Workspace name length.
- Description length.
- UUID format.
- Chapter status values.
- Parent-child relationships.
- Pagination limits.
- Sorting fields.
- Enum values.

Use allowlists for fields that can be sorted or filtered.

Never construct SQL queries through string concatenation using user input.

Use SQLAlchemy's parameterised query mechanisms.

## 14.4 Cross-Site Scripting (XSS)

- Avoid unsafe HTML rendering.
- Escape untrusted content.
- Use React's normal text rendering.
- Sanitize user-generated rich text if rich-text functionality is introduced.
- Apply a Content Security Policy.
- Avoid unnecessary third-party scripts.

## 14.5 Cross-Site Request Forgery (CSRF)

Because authentication uses cookies:

- Implement CSRF protection for state-changing operations.
- Validate request origin where appropriate.
- Use suitable SameSite cookie settings.
- Never treat CORS as a CSRF defence.

## 14.6 Cross-Origin Resource Sharing (CORS)

Configure an explicit allowlist of frontend origins.

Do not use wildcard origins with credentialed requests.

Only allow required HTTP methods and headers.

## 14.7 Database security

- Use a dedicated application database account.
- Do not connect using PostgreSQL superuser credentials.
- Grant only the permissions the application needs.
- Use parameterised queries.
- Protect database connection strings.
- Use encrypted database connections in production.
- Restrict database network access.
- Use backups and test restoration.
- Avoid exposing the database port publicly.
- Use migrations for schema changes.

## 14.8 Secret management

Never hardcode:

- Database passwords.
- Session secrets.
- Email-provider credentials.
- API keys.
- Encryption keys.
- Cloud-storage credentials.

Use environment variables during local development and a proper secrets manager in production.

Create a `.env.example` file containing placeholder names, never real secrets.

Add `.env` to `.gitignore`.

If a secret is accidentally committed, rotate it. Removing it from the latest commit alone is insufficient.

## 14.9 Transport and encryption

- Enforce HTTPS in production.
- Use TLS for external service communication.
- Use encrypted storage provided by the cloud infrastructure.
- Protect backups with encryption.
- Use a managed key-management service where appropriate.
- Avoid storing sensitive information unnecessarily.

Password hashes must be protected, but they are not reversible encryption.

## 14.10 Logging and monitoring

Log important events:

- Login success and failure.
- Logout.
- Password changes.
- Password-reset requests.
- Email changes.
- Session revocation.
- Account deletion requests.
- Administrative or security-sensitive actions.

Do not log:

- Passwords.
- Session cookies.
- Authentication tokens.
- Password-reset tokens.
- API keys.
- Full sensitive request bodies.
- Private academic content unless there is a specific, justified need.

Use structured logs with timestamps, event types and correlation IDs.

Restrict access to security logs and define retention periods.

## 14.11 Rate limiting and abuse prevention

Implement rate limits for:

- Registration.
- Login.
- Password recovery.
- Email verification.
- Resource creation.
- Expensive or potentially abusive API operations.

Use appropriate limits per account and IP address, with proxy configuration handled carefully.

Return HTTP 429 when rate limits are exceeded.

## 14.12 Data privacy

Axonweave will eventually process academic materials, personal information and potentially unpublished research.

Therefore:

- Collect only necessary personal information.
- Explain why data is collected.
- Define data retention periods.
- Allow users to export their data.
- Provide a deletion workflow.
- Restrict access to personal data.
- Do not expose user data in public URLs.
- Do not use private user content for model training without appropriate consent and a clear legal basis.
- Ensure future AI providers' data-retention and processing terms are reviewed before sending user content to them.

For India, assess applicable obligations under the Digital Personal Data Protection Act, 2023 and rules and notifications in force at deployment time. Do not assume that a generic privacy policy alone establishes compliance.

## 14.13 Account deletion

Implement an explicit account deletion workflow.

It should:

1. Require an authenticated user.
2. Require appropriate confirmation or re-authentication.
3. Explain what data will be deleted.
4. Define what happens to associated workspaces and academic content.
5. Remove or anonymise applicable personal data.
6. Revoke active sessions.
7. Invalidate outstanding reset and verification tokens.
8. Process deletion of associated stored files when those features are introduced.
9. Respect legally required retention exceptions.
10. Record completion without retaining unnecessary personal content.

---

# 15. Future AI Readiness

Although LLM integration is not part of Phase 1, the architecture must support it.

Do not tightly couple the application to OpenAI, Gemini, Claude or any other provider.

Create a future AI service boundary.

Suggested backend structure:

```text
app/
|
+-- api/
|   +-- v1/
|
+-- core/
|   +-- config.py
|   +-- security.py
|   +-- logging.py
|
+-- models/
|
+-- schemas/
|
+-- repositories/
|
+-- services/
|
+-- modules/
|   +-- auth/
|   +-- users/
|   +-- workspaces/
|   +-- subjects/
|   +-- folders/
|   +-- chapters/
|   +-- dashboard/
|
+-- ai/
|   +-- providers/
|   +-- orchestration/
|   +-- prompts/
|
+-- database/
|
+-- tests/
|
+-- main.py
```

The `ai` package may initially contain only interfaces or remain unimplemented. Do not add unnecessary AI dependencies in Phase 1.

Later, it should support:

- Multiple model providers.
- Model selection.
- Structured responses.
- Streaming responses.
- Tool calling.
- Usage tracking.
- Cost tracking.
- Prompt versioning.
- Evaluation.

The application must continue working when no LLM provider is configured.

---

# 16. Frontend Project Structure

Use a feature-oriented structure.

```text
frontend/
|
+-- src/
|   |
|   +-- app/
|   |   +-- (auth)/
|   |   |   +-- login/
|   |   |   +-- register/
|   |   |   +-- forgot-password/
|   |   |
|   |   +-- (dashboard)/
|   |   |   +-- dashboard/
|   |   |   +-- workspaces/
|   |   |   +-- subjects/
|   |   |   +-- settings/
|   |   |
|   |   +-- layout.tsx
|   |   +-- page.tsx
|   |
|   +-- components/
|   |   +-- ui/
|   |   +-- layout/
|   |   +-- forms/
|   |   +-- workspace/
|   |
|   +-- features/
|   |   +-- auth/
|   |   +-- profile/
|   |   +-- workspaces/
|   |   +-- subjects/
|   |   +-- folders/
|   |   +-- chapters/
|   |
|   +-- lib/
|   |   +-- api/
|   |   +-- validation/
|   |   +-- utils/
|   |
|   +-- hooks/
|   +-- types/
|   +-- styles/
|
+-- package.json
```

Use:

- TypeScript types for API data.
- Reusable components.
- Centralised API client.
- Consistent form validation.
- Error boundaries where appropriate.
- Accessible semantic HTML.
- Loading and empty states.
- Responsive layouts.

Do not put authentication secrets in frontend environment variables. Any environment variable exposed to browser code must be treated as public.

---

# 17. Backend Project Structure

```text
backend/
|
+-- app/
|   |
|   +-- api/
|   |   +-- v1/
|   |       +-- router.py
|   |
|   +-- core/
|   |   +-- config.py
|   |   +-- security.py
|   |   +-- dependencies.py
|   |   +-- logging.py
|   |
|   +-- database/
|   |   +-- connection.py
|   |   +-- base.py
|   |
|   +-- models/
|   |
|   +-- schemas/
|   |
|   +-- repositories/
|   |
|   +-- services/
|   |
|   +-- modules/
|   |   +-- auth/
|   |   +-- users/
|   |   +-- workspaces/
|   |   +-- subjects/
|   |   +-- folders/
|   |   +-- chapters/
|   |   +-- dashboard/
|   |
|   +-- main.py
|
+-- alembic/
+-- tests/
+-- requirements.txt
+-- Dockerfile
```

Use separate layers:

- Models: database representation.
- Schemas: request and response validation.
- Repositories: database queries.
- Services: business logic.
- API routes: HTTP request handling.

Do not put all application logic inside route handlers.

---

# 18. Development and Deployment Environment

## 18.1 Local development

Use Docker Compose for PostgreSQL and other required infrastructure.

Recommended initial setup:

```text
axonweave/
|
+-- frontend/
+-- backend/
+-- infrastructure/
+-- documentation/
+-- docker-compose.yml
+-- .gitignore
+-- .env.example
+-- README.md
```

The development environment should support starting the frontend, backend and database consistently.

## 18.2 Environment configuration

Example environment variable names:

```env
APP_ENV=development
APP_SECRET_KEY=replace_with_secure_random_value

DATABASE_URL=postgresql+psycopg://...

FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000

COOKIE_SECURE=false
COOKIE_SAMESITE=lax

EMAIL_PROVIDER=
EMAIL_API_KEY=
```

This is an illustrative configuration only. Generate actual secrets securely and never commit a populated `.env` file.

Validate required production settings at application startup. Fail safely when critical configuration is missing.

## 18.3 Environments

Maintain separate:

- Development.
- Testing.
- Staging.
- Production.

Do not use production user data in development or automated tests without a properly approved anonymisation process.

## 18.4 Production deployment

Before production:

- Configure HTTPS.
- Restrict database access.
- Configure secure cookies.
- Set production CORS origins.
- Configure secrets management.
- Enable backups.
- Configure monitoring.
- Apply database migrations through a controlled deployment process.
- Disable development-only debugging features.
- Configure email delivery.
- Configure security headers.
- Test rollback and recovery procedures.

---

# 19. Testing Requirements

Testing must be part of development, not something postponed until the end.

## 19.1 Backend tests

Test:

- Registration.
- Duplicate email rejection.
- Password hashing.
- Login success and failure.
- Logout.
- Session expiration.
- Password reset.
- Email verification.
- Workspace creation.
- Subject creation.
- Folder creation.
- Chapter creation.
- Ownership validation.
- Invalid parent-child relationships.
- Deletion and archival.
- Pagination and filtering.

## 19.2 Security tests

Essential test cases:

1. User A cannot access User B's workspace.
2. User A cannot edit User B's subject.
3. User A cannot delete User B's chapter.
4. An unauthenticated user cannot access protected endpoints.
5. An expired session cannot access protected resources.
6. A revoked session cannot be reused.
7. Invalid password-reset tokens are rejected.
8. A password-reset token cannot be reused.
9. Invalid input is rejected.
10. SQL injection attempts do not alter database queries.
11. Cross-origin requests cannot bypass CSRF protection.
12. Rate limits are enforced.

## 19.3 Frontend tests

Test:

- Registration form validation.
- Login form validation.
- Navigation.
- Sidebar behaviour.
- Dashboard loading.
- Workspace creation.
- Subject creation.
- Folder creation.
- Chapter creation.
- Profile editing.
- Settings.
- Mobile responsiveness.
- Error and empty states.

## 19.4 Integration tests

Verify the complete user journey:

```text
Register
   |
   v
Verify email
   |
   v
Login
   |
   v
Create workspace
   |
   v
Create subject
   |
   v
Create folder
   |
   v
Create chapter
   |
   v
Refresh application
   |
   v
Verify saved data
   |
   v
Logout
```

---

# 20. UI/UX Design Requirements

The interface should look like a modern academic productivity platform.

Design direction:

- Clean and minimal.
- Professional.
- Calm and focused.
- Consistent spacing.
- Strong typography hierarchy.
- Clear navigation.
- Responsive layout.
- Accessible colour contrast.
- Consistent buttons, inputs, cards and dialogs.

Avoid:

- Excessive gradients.
- Unnecessary animations.
- Overloaded dashboards.
- Too many colours.
- Decorative statistics that do not represent real data.
- Placeholder buttons that do nothing.

Use a reusable design system with consistent:

- Colours.
- Typography.
- Spacing.
- Border radii.
- Shadows.
- Form controls.
- Modal dialogs.
- Toast notifications.
- Confirmation dialogs.

Support keyboard navigation and visible focus indicators.

---

# 21. Implementation Order

Build the project in the following order.

## Step 1 — Project setup

- Create Git repository.
- Create frontend project.
- Create backend project.
- Configure PostgreSQL.
- Configure Docker Compose.
- Configure environment variables.
- Configure linting and formatting.
- Add README documentation.

**Deliverable:** Both frontend and backend run locally and can communicate.

## Step 2 — Database foundation

- Configure SQLAlchemy.
- Create database connection.
- Configure Alembic.
- Create initial database models.
- Define foreign keys and indexes.
- Create initial migration.
- Verify database persistence.

**Deliverable:** Database schema is working and version-controlled.

## Step 3 — Authentication

- Implement registration.
- Implement password hashing.
- Implement login.
- Implement session management.
- Implement logout.
- Implement current-user endpoint.
- Implement CSRF protection.
- Implement login rate limiting.
- Implement email verification and password recovery.

**Deliverable:** Users can securely register, verify, log in and log out.

## Step 4 — Application layout

- Create dashboard layout.
- Create sidebar.
- Create header.
- Create profile menu.
- Create responsive navigation.
- Create protected routes.

**Deliverable:** Authenticated users can navigate the application.

## Step 5 — Workspace management

- Implement workspace APIs.
- Create workspace UI.
- Implement workspace list.
- Implement creation.
- Implement editing.
- Implement archiving.
- Implement deletion.

**Deliverable:** Users can manage their own workspaces.

## Step 6 — Subject management

- Implement subject APIs.
- Create subject list.
- Create subject form.
- Implement subject details.
- Implement edit and delete.

**Deliverable:** Users can manage subjects inside workspaces.

## Step 7 — Folder and chapter management

- Implement folder APIs.
- Implement chapter APIs.
- Create folder hierarchy.
- Create chapter management interface.
- Implement sorting and movement.
- Validate parent-child relationships.

**Deliverable:** Users can organise academic subjects into folders and chapters.

## Step 8 — Dashboard integration

- Fetch real workspace information.
- Display subject counts.
- Display recent activity.
- Display recently updated subjects.
- Add loading and error states.

**Deliverable:** Dashboard reflects actual user data.

## Step 9 — Security review

- Verify ownership checks.
- Test session security.
- Test CSRF protection.
- Test rate limiting.
- Test input validation.
- Check secrets and environment configuration.
- Review logging.
- Run dependency vulnerability checks.

**Deliverable:** Security issues identified and resolved before release.

## Step 10 — Final testing and documentation

- Run backend tests.
- Run frontend tests.
- Run integration tests.
- Test responsive layouts.
- Document APIs.
- Document environment setup.
- Document database migrations.
- Document deployment steps.

**Deliverable:** Phase 1 is ready for the next development phase.

---

# 22. Phase 1 Acceptance Criteria

Phase 1 is complete only when the following conditions are satisfied.

## Authentication

- [ ] User can register.
- [ ] Duplicate email registration is prevented.
- [ ] Passwords are securely hashed.
- [ ] Email verification works.
- [ ] User can log in.
- [ ] User can log out.
- [ ] Session expiration works.
- [ ] Password reset works.
- [ ] Protected APIs reject unauthenticated requests.

## Dashboard

- [ ] Dashboard displays real user information.
- [ ] Sidebar navigation works.
- [ ] Responsive layouts work.
- [ ] Loading and error states are implemented.

## Profile and settings

- [ ] User can view their profile.
- [ ] User can edit permitted profile details.
- [ ] User can change their password.
- [ ] User can manage sessions.
- [ ] Account deletion workflow is defined and implemented.

## Workspace

- [ ] User can create a workspace.
- [ ] User can view their workspaces.
- [ ] User can edit a workspace.
- [ ] User can archive and restore a workspace.
- [ ] User can delete a workspace.

## Academic organisation

- [ ] User can create subjects.
- [ ] User can create folders.
- [ ] User can create chapters.
- [ ] User can edit and delete academic items.
- [ ] Folder and chapter relationships are valid.
- [ ] Search and sorting work.

## Data protection

- [ ] User A cannot access User B's data.
- [ ] All protected APIs enforce authorization.
- [ ] Database credentials are not exposed.
- [ ] Secrets are not committed to Git.
- [ ] Sensitive information is excluded from logs.
- [ ] CSRF and rate limiting are implemented.
- [ ] HTTPS and secure cookies are configured for production.
- [ ] Backup and restoration procedures are tested.

## Code quality

- [ ] Frontend and backend are separated.
- [ ] Backend follows modular architecture.
- [ ] Database migrations work.
- [ ] API documentation is available.
- [ ] Tests pass.
- [ ] Setup documentation is complete.

---

# 23. Features Explicitly Outside Phase 1

Do not implement the following yet:

- LLM chat and model integrations.
- RAG.
- Embedding generation.
- Vector search.
- PDF and PPTX content processing.
- AI-generated summaries.
- Flashcards and quizzes.
- Spaced repetition.
- Adaptive learner intelligence.
- Knowledge graph generation.
- Research-paper analysis.
- Audio generation.
- Speech recognition.
- AI agents.
- Research collaboration.

However, Phase 1 must be designed so that these features can be added without restructuring the entire application.

---

# 24. Final Development Instruction

Build Axonweave as a real, secure, extensible academic web application—not as a static UI demonstration.

Follow the specified technology stack and architecture. Implement features incrementally, starting with project configuration, database foundations and authentication.

For every feature:

1. Design the database model.
2. Create the migration.
3. Implement backend schemas.
4. Implement repository and service logic.
5. Implement API routes.
6. Add authentication and ownership checks.
7. Add backend tests.
8. Build the frontend interface.
9. Connect the frontend to the API.
10. Add frontend and integration tests.
11. Verify the complete workflow.

Do not skip backend functionality by hardcoding frontend data.

Do not create buttons that do not perform real operations.

Do not leave security controls as TODO comments.

Do not expose secrets or sensitive user information.

Do not implement future AI functionality prematurely.

Keep the code modular, readable, documented and testable.

When a feature is complete, verify its acceptance criteria before moving to the next feature.

**Final outcome:** A fully functional, secure and responsive Axonweave application foundation, with authentication, user management, workspaces, subjects, folders, chapters, dashboard and a database-backed backend—ready for Phase 2, the integration of LLM-powered academic intelligence.