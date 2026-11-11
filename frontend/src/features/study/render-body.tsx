import type { MaterialSource, StudyMaterial } from "@/lib/api/study";
import { FormulaView, GuideView, SummaryView } from "./material-views";

/**
 * Read-only rendering of a stored payload, used for previews and old versions (the live views
 * for glossary, deck and bank read through their own endpoints).
 */
export function renderBody(
  material: StudyMaterial,
  payload: unknown,
  sources: MaterialSource[],
  onRegenerateSection?: (i: number) => void,
) {
  const unavailable = material.unavailable_document_ids ?? [];
  switch (material.resource_type) {
    case "summary":
      return (
        <SummaryView
          payload={payload as never}
          sources={sources}
          unavailable={unavailable}
          onRegenerateSection={onRegenerateSection}
        />
      );
    case "study_guide":
      return <GuideView payload={payload as never} sources={sources} unavailable={unavailable} />;
    case "formula_sheet":
      return <FormulaView payload={payload as never} sources={sources} unavailable={unavailable} />;
    case "glossary": {
      const terms = (payload as { terms?: { term: string; definition: string }[] }).terms ?? [];
      return (
        <dl className="space-y-2 text-sm">
          {terms.map((t, i) => (
            <div key={i}>
              <dt className="font-medium break-words">{t.term}</dt>
              <dd className="break-words">{t.definition}</dd>
            </div>
          ))}
        </dl>
      );
    }
    default:
      return null;
  }
}
