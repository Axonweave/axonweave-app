"""Embedding column definition shared by the model, the migration and the config check.

This is the single source of truth for the vector dimension (D-69). It is provisional until the
embedding model is verified in M4 (scripts/list_embedding_models.py): a different dimension means a
new migration and a new `index_version`, never a silent change. Embeddings of different models or
dimensions are never mixed in one index.
"""

EMBEDDING_COLUMN_DIMENSIONS = 768
