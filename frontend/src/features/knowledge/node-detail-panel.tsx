"use client";

import Link from "next/link";
import { useState } from "react";
import { AsyncSection } from "@/components/ui/async-section";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsync } from "@/hooks/use-async";
import { useToast } from "@/hooks/use-toast";
import { ApiRequestError } from "@/lib/api/client";
import {
  NODE_TYPES,
  RELATIONSHIP_LABELS,
  evidenceHref,
  knowledgeApi,
  type KnowledgeNodeDetail,
  type NodeType,
} from "@/lib/api/knowledge";

const FIELD = "border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm";

function Related({
  title,
  items,
  onSelect,
}: {
  title: string;
  items: KnowledgeNodeDetail["related"];
  onSelect: (id: string) => void;
}) {
  if (!items?.length) return null;
  return (
    <div>
      <h4 className="text-muted-foreground text-xs font-medium uppercase">{title}</h4>
      <ul className="mt-1 space-y-1">
        {items.map(({ node, edge }) => (
          <li key={edge.id} className="flex items-center justify-between gap-2 text-sm">
            <button
              type="button"
              className="text-primary text-left hover:underline"
              onClick={() => onSelect(node.id)}
            >
              {node.name}
            </button>
            <span className="text-muted-foreground text-xs">
              {RELATIONSHIP_LABELS[edge.relationship_type] ?? edge.relationship_type}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EditForm({
  node,
  onDone,
}: {
  node: KnowledgeNodeDetail;
  onDone: (changed: boolean) => void;
}) {
  const { toast } = useToast();
  const [name, setName] = useState(node.name);
  const [type, setType] = useState<NodeType>(node.node_type as NodeType);
  const [definition, setDefinition] = useState(node.definition ?? "");
  const [aliases, setAliases] = useState((node.aliases ?? []).join(", "));
  const [saving, setSaving] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await knowledgeApi.updateNode(node.id, {
        name: name.trim(),
        node_type: type,
        definition: definition.trim() || null,
        aliases: aliases
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
      });
      toast({ title: "Concept saved" });
      onDone(true);
    } catch (err) {
      const message =
        err instanceof ApiRequestError && err.status === 409
          ? "Another concept already uses that name or alias."
          : "Could not save this concept.";
      toast({ title: message, variant: "destructive" });
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-3" aria-label="Edit concept">
      <label className="block text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Name</span>
        <input
          className={FIELD}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={200}
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Type</span>
        <select
          className={FIELD}
          value={type}
          onChange={(e) => setType(e.target.value as NodeType)}
        >
          {NODE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Definition</span>
        <textarea
          className={FIELD}
          rows={3}
          value={definition}
          onChange={(e) => setDefinition(e.target.value)}
          maxLength={2000}
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted-foreground mb-1 block text-xs">Aliases (comma separated)</span>
        <input className={FIELD} value={aliases} onChange={(e) => setAliases(e.target.value)} />
      </label>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving || !name.trim()}>
          Save
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => onDone(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function NodeDetailPanel({
  nodeId,
  onSelect,
  onChanged,
  onExpand,
  onClose,
}: {
  nodeId: string;
  onSelect: (id: string) => void;
  onChanged: () => void;
  onExpand: (id: string) => void;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const detail = useAsync(() => knowledgeApi.node(nodeId), [nodeId]);
  const evidence = useAsync(() => knowledgeApi.nodeEvidence(nodeId, 10, 0), [nodeId]);
  const [editing, setEditing] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const node = detail.data;

  async function archive() {
    try {
      await knowledgeApi.archiveNode(nodeId);
      toast({ title: "Concept archived" });
      onChanged();
      onClose();
    } catch {
      toast({ title: "Could not archive this concept.", variant: "destructive" });
    }
  }

  return (
    <aside aria-label="Concept details" className="bg-card min-w-0 space-y-4 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-foreground text-lg font-semibold break-words">
          {node?.name ?? "Concept"}
        </h2>
        <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close details">
          Close
        </Button>
      </div>
      <AsyncSection
        title="Details"
        loading={detail.loading}
        error={detail.error}
        onRetry={detail.reload}
        isEmpty={!node}
        empty={<p className="text-muted-foreground text-sm">Concept not found.</p>}
      >
        {node ? (
          editing ? (
            <EditForm
              node={node}
              onDone={(changed) => {
                setEditing(false);
                if (changed) {
                  detail.reload();
                  onChanged();
                }
              }}
            />
          ) : (
            <div className="space-y-3">
              <p className="text-muted-foreground text-xs">
                {node.node_type}
                {node.difficulty ? ` · ${node.difficulty}` : ""} · {node.origin}
                {node.edited_by_user ? " · edited by you" : ""}
              </p>
              {node.definition ? <p className="text-sm">{node.definition}</p> : null}
              {(node.aliases?.length ?? 0) ? (
                <p className="text-sm">
                  <span className="text-muted-foreground">Also known as: </span>
                  {(node.aliases ?? []).join(", ")}
                </p>
              ) : null}
              <Related title="Prerequisites" items={node.prerequisites} onSelect={onSelect} />
              <Related title="Builds toward" items={node.dependents} onSelect={onSelect} />
              <Related title="Related" items={node.related} onSelect={onSelect} />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => onExpand(node.id)}>
                  Expand neighbours
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button size="sm" variant="outline" onClick={() => setConfirmArchive(true)}>
                  Archive
                </Button>
              </div>
            </div>
          )
        ) : null}
      </AsyncSection>

      <AsyncSection
        title="Source evidence"
        loading={evidence.loading}
        error={evidence.error}
        onRetry={evidence.reload}
        isEmpty={!evidence.data?.data.length}
        empty={
          <p className="text-muted-foreground text-sm">
            No source evidence yet. This concept was added without a document passage.
          </p>
        }
      >
        <ul className="space-y-3">
          {evidence.data?.data.map((ev) => (
            <li key={ev.id} className="text-sm">
              <blockquote className="border-l-2 pl-2 italic">“{ev.quote}”</blockquote>
              <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-xs">
                <Link href={evidenceHref(ev)} className="text-primary hover:underline">
                  {ev.document_name}
                </Link>
                {ev.page_number ? <span>page {ev.page_number}</span> : null}
                {ev.slide_number ? <span>slide {ev.slide_number}</span> : null}
                {ev.stale ? <span className="text-amber-600">source changed</span> : null}
              </div>
            </li>
          ))}
        </ul>
      </AsyncSection>

      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={setConfirmArchive}
        title="Archive this concept?"
        description="It will be hidden from the graph. You can restore it later from the archived list."
        confirmLabel="Archive"
        destructive
        onConfirm={archive}
      />
    </aside>
  );
}
