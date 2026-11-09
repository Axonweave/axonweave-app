# Backup and restore (PostgreSQL)

This procedure was **run for real** on the local Docker Compose dev database on 2026-11-04 and
the restored data was checked against the source. The commands below are the ones that were run.
It has **not** been run against a production or hosted database.

Scope: the only state in Phase 1 is the PostgreSQL database (Redis is not used; there is no file
storage). Backing up the database is a complete backup.

## What a dump contains (and does not)

- `pg_dump -Fc` (custom format) contains schema, data, indexes, constraints and the `GRANT`s on
  tables. It does **not** contain roles. The roles `axonweave_owner` and `axonweave_app`
  (decision D-33) must already exist on the target server. In Compose they are created by
  `infrastructure/docker/init-db.sql` the first time the Postgres volume is initialised.
- The dump holds personal data and password hashes. Treat the file as sensitive: do not commit it,
  store it encrypted, restrict who can read it, and delete old copies.

## Backup

Run from the repository root with the stack up. `axonweave_owner` is the owner role; the
restricted `axonweave_app` role is not used for backups.

```bash
docker compose exec -T postgres pg_dump -U axonweave_owner -d axonweave -Fc -f /tmp/axonweave.dump
docker compose cp postgres:/tmp/axonweave.dump ./axonweave-$(date +%Y%m%d-%H%M%S).dump
docker compose exec -T postgres rm -f /tmp/axonweave.dump
```

Result on 2026-11-04: `pg_dump exit=0`, dump size 61,800 bytes.

(The run recorded here kept the file inside the container and restored from there; the
`docker compose cp` line is the extra step to get it onto the host and was not exercised.)

## Restore

Restore into an empty database. To rehearse, use a scratch database name so live data is untouched:

```bash
docker compose exec -T postgres psql -U axonweave_owner -d postgres \
  -c "CREATE DATABASE axonweave_restore_test"
docker compose exec -T postgres pg_restore -U axonweave_owner -d axonweave_restore_test \
  --no-owner --exit-on-error /tmp/axonweave.dump
```

Result: `pg_restore exit=0` with `--exit-on-error`, so there were no skipped objects.

For a real recovery, restore into a new empty `axonweave` database (stop the backend first, create
the database, run the same `pg_restore` with `-d axonweave`), then start the backend. Do not
restore on top of a database that still holds data.

On Windows Git Bash prefix the commands with `MSYS_NO_PATHCONV=1`, otherwise `/tmp/...` is
rewritten into a Windows path and the dump fails with "could not open output file".

## Verification that was performed

Compared the source database `axonweave` with the restored `axonweave_restore_test`:

| Check | Source | Restored |
| --- | --- | --- |
| rows: users / workspaces / subjects / folders / chapters / sessions / activity_logs | 36 / 66 / 2 / 2 / 2 / 23 / 96 | 36 / 66 / 2 / 2 / 2 / 23 / 96 |
| `alembic_version` | `0001` | `0001` |
| md5 of workspace `id\|\|name` (ordered) | `19ccf463...97aa347d97c0b31a19c` | identical |
| md5 of user `id\|\|email\|\|password_hash` (ordered) | `e5c0914b...bd141bbe5ad` | identical |
| md5 of chapter `id\|\|title` (ordered) | `99e497a2...b10` | identical |
| indexes in `public` | 52 | 52 |
| constraints in `public` | 35 | 35 |

The restricted application role could read the restored data (`select count(*) from workspaces`
as `axonweave_app` returned 66), so table grants survive the dump.

Cleanup afterwards: `DROP DATABASE axonweave_restore_test` and the dump removed from the container.

## Not verified

- The backend application was not started against the restored database. Only SQL-level checks
  above were made.
- Restore onto a brand-new Postgres server or volume (roles created by `init-db.sql` first) was
  not rehearsed.
- No scheduled backups, retention policy, off-site copy or encryption exist. Those are deployment
  work (see `docs/DEPLOYMENT.md`).
- Point-in-time recovery (WAL archiving) is not set up; recovery granularity is the last dump.

## Phase 3: object store
Documents live in the object store, metadata, chunks and vectors in PostgreSQL. Back up both at the same point in time.
After restoring only the database, rows can point at missing objects (downloads fail, text and search still work); after
restoring only the object store, orphan objects are harmless but unreferenced. Deleted documents queue object removal in
`storage_cleanup`; do not restore a bucket snapshot older than the database without re-running cleanup review. Vectors can be
rebuilt with `scripts/reindex_documents.py` if a different embedding model is chosen.
