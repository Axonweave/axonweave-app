"""Formula sheet generator (spec 10): LaTeX validation, variable definitions, source references.

A syntactically valid formula is NOT claimed to be correct (10.4). Unsafe expressions are dropped,
syntax problems and undefined variables are kept but flagged `needs_review`, and every entry keeps
its source references so the student can compare it with the original.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.latex import MAX_EXPRESSION, check_latex, defined_symbol, variable_symbols
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_duplicates

MAX_FORMULAS = 60


class FormulaSettings(GeneratorSettings):
    max_formulas: int = Field(default=20, ge=1, le=MAX_FORMULAS)
    include_examples: bool = True
    include_units: bool = True
    include_conditions: bool = True


class VariableOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Annotated[CleanStr, Field(min_length=1, max_length=40)]
    meaning: Annotated[CleanStr, Field(min_length=1, max_length=300)]
    unit: Annotated[CleanStr, Field(max_length=60)] = ""


class FormulaOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    expression: Annotated[CleanStr, Field(min_length=1, max_length=MAX_EXPRESSION + 20)]
    explanation: Annotated[CleanStr, Field(max_length=1500)] = ""
    variables: list[VariableOut] = Field(default_factory=list, max_length=30)
    conditions: Annotated[CleanStr, Field(max_length=800)] = ""
    example: Annotated[CleanStr, Field(max_length=1200)] = ""
    topic: Annotated[CleanStr, Field(max_length=120)] = ""
    source_refs: list[int] = Field(default_factory=list, max_length=20)
    # Set by the backend (never trusted from the model): see `_assess`.
    needs_review: bool = False
    review_notes: list[str] = Field(default_factory=list, max_length=10)


class FormulaSheetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    formulas: list[FormulaOut] = Field(min_length=1, max_length=MAX_FORMULAS)
    # Derived by the backend in `dump` (never trusted from the model or an edit); declared so a
    # stored payload round-trips through the edit endpoint.
    verification: Literal["unverified"] = "unverified"
    flagged_count: int = Field(default=0, ge=0, le=MAX_FORMULAS)


_SHAPE = (
    'Return JSON: {"title": string, "formulas": [{"name": string, "expression": string (LaTeX '
    'math only), "explanation": string, "variables": [{"symbol": string, "meaning": string, '
    '"unit": string}], "conditions": string, "example": string, "topic": string, '
    '"source_refs": [integer]}]}'
)


def _checked(settings: GeneratorSettings) -> FormulaSettings:
    assert isinstance(settings, FormulaSettings)
    return settings


def _assess(formula: FormulaOut) -> bool:
    """Normalise the expression and set the review flags. Returns False for an unsafe entry."""
    check = check_latex(formula.expression)
    if check.dangerous:
        return False
    formula.expression = check.expression
    notes = list(check.issues)
    if formula.variables or variable_symbols(check.expression):
        defined = {defined_symbol(v.symbol) for v in formula.variables}
        if variable_symbols(check.expression) - defined:
            notes.append("undefined_variables")
    if not formula.source_refs:
        notes.append("no_source_reference")
    formula.review_notes = list(dict.fromkeys(notes))
    formula.needs_review = bool(formula.review_notes)
    return True


class FormulaSheetGenerator(Generator):
    key = "formula_sheet"
    resource_type = "formula_sheet"
    prompt_key = prompts.FORMULA_SHEET_KEY
    settings_model = FormulaSettings
    output_model = FormulaSheetOutput
    source_mode = "ordered"
    allow_sampled_fallback = True
    min_source_tokens = 20
    max_output_tokens: ClassVar[int | None] = 8000

    def instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        return (
            f"TASK\nList at most {s.max_formulas} formulas that appear in the material, in "
            f"{s.language}. Copy each expression as the material gives it. "
            + (
                "Give the unit of each variable where the material does. "
                if s.include_units
                else ""
            )
            + (
                "State the conditions of use the material gives. "
                if s.include_conditions
                else "Leave 'conditions' empty. "
            )
            + (
                "Add a short worked example only if the material has one.\n"
                if s.include_examples
                else "Leave 'example' empty.\n"
            )
            + _SHAPE
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def _clean(self, output: Any, source_count: int) -> list[FormulaOut]:
        kept: list[FormulaOut] = []
        for f in output.formulas:
            f.source_refs = clean_refs(f.source_refs, source_count)
            if _assess(f):  # unsafe expressions are dropped, never stored or rendered
                kept.append(f)
        return kept

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        if len(output.formulas) > s.max_formulas:
            raise OutputInvalid("formulas: more formulas than requested")
        kept = [f for f in self._clean(output, source_count) if f.source_refs]
        if not kept:
            raise OutputInvalid("formulas: no safe formula is supported by a source")
        if find_duplicates([f.expression for f in kept]) or find_duplicates([f.name for f in kept]):
            raise OutputInvalid("formulas: duplicate formulas")
        for f in kept:
            if not s.include_units:
                for v in f.variables:
                    v.unit = ""
            if not s.include_conditions:
                f.conditions = ""
            if not s.include_examples:
                f.example = ""
        output.formulas = kept
        return output

    def validate_edit(self, output: Any, source_count: int) -> Any:
        """A user may keep a flagged formula (flags are recomputed) but never an unsafe one."""
        kept = self._clean(output, source_count)
        if len(kept) != len(output.formulas):
            raise OutputInvalid("formulas: an expression contains unsafe content")
        if find_duplicates([f.name for f in kept]):
            raise OutputInvalid("formulas: duplicate formulas")
        output.formulas = kept
        return output

    def item_count(self, output: Any) -> int:
        return len(output.formulas)

    def dump(self, output: Any) -> dict[str, Any]:
        data: dict[str, Any] = output.model_dump(mode="json")
        # Fixed statement for the UI: a valid expression is not proof of correctness (10.4).
        data["verification"] = "unverified"
        data["flagged_count"] = sum(1 for f in output.formulas if f.needs_review)
        return data
