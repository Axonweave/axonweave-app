"""Composite foreign key with `ON DELETE SET NULL (column)` (PostgreSQL 15+).

SQLAlchemy only emits plain `SET NULL`, which on a composite key would also null the NOT NULL owner
column. This subclass renders the column list so only the listed columns are cleared (D-53, D-61).
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import ForeignKeyConstraint


class SetNullColumnsFK(ForeignKeyConstraint):
    def __init__(
        self,
        columns: Sequence[str],
        refcolumns: Sequence[str],
        *,
        set_null: Sequence[str],
        **kwargs: Any,
    ) -> None:
        super().__init__(columns, refcolumns, ondelete="SET NULL", **kwargs)
        self.set_null = tuple(set_null)


@compiles(SetNullColumnsFK, "postgresql")
def _compile_set_null_fk(constraint: SetNullColumnsFK, compiler: Any, **kw: Any) -> str:
    text: str = compiler.visit_foreign_key_constraint(constraint, **kw)
    cols = ", ".join(compiler.preparer.quote(c) for c in constraint.set_null)
    return text.replace(" ON DELETE SET NULL", f" ON DELETE SET NULL ({cols})", 1)
