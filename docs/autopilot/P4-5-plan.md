# P4-5 plan (backend only)
Already present from M1-M4: edit/versions/restore/regenerate preview+apply (D-92), preferences table (D-89).
New in M5:
1. Migration 0008 `study_exports` (+grants). Model, repository.
2. Library: `GET /study/materials` (q, type, workspace, subject, chapter, status, archived, allow-listed sort, pagination), `DELETE`, `POST duplicate|archive|unarchive`; unavailable-source marking when a document is deleted.
3. Preferences: `GET/PUT /study/preferences`; used as generation defaults (only where the generator accepts the key and the request did not set it).
4. Export: `POST /study/materials/{id}/export`, `GET /study/exports/{id}`, `GET /study/exports/{id}/download`. Celery task renders (PDF via PyMuPDF, CSV, Markdown, DOCX), stores in private storage, expiry sweeper. CSV formula neutralisation; PDF is plain text (no HTML); quiz/bank exports never hold answer keys.
5. Account export includes study data; account deletion cascades and queues export objects for cleanup.
6. Tests per list in TASKS_Phase4 M5. Not in scope: favourites (no column; not in M5 list), quiz/bank duplicate.
