import React, { useMemo } from 'react';
import { Link2, Trash2, X } from 'lucide-react';
import type { LogicEdge, LogicNode, NodeType } from './types';

export const LogicChainDetails: React.FC<{
  items: LogicNode[];
  selectedId: string;
  edges: LogicEdge[];
  draftTitle: string;
  draftSummary: string;
  draftType: NodeType;
  draftMin: number;
  linkTo: string;
  linkReason: string;
  onDraftTitle: (v: string) => void;
  onDraftSummary: (v: string) => void;
  onDraftType: (v: NodeType) => void;
  onDraftMin: (v: number) => void;
  onLinkTo: (v: string) => void;
  onLinkReason: (v: string) => void;
  onCommit: () => void;
  onSetEdges: (edges: LogicEdge[]) => void;
  onClose?: () => void;
}> = ({
  items,
  selectedId,
  edges,
  draftTitle,
  draftSummary,
  draftType,
  draftMin,
  linkTo,
  linkReason,
  onDraftTitle,
  onDraftSummary,
  onDraftType,
  onDraftMin,
  onLinkTo,
  onLinkReason,
  onCommit,
  onSetEdges,
  onClose,
}) => {
  const selectedNode = useMemo(() => items.find((n) => n.node_id === selectedId) || null, [items, selectedId]);
  const idToTitle = useMemo(() => new Map(items.map((n) => [n.node_id, n.title])), [items]);

  const referenceEdges = useMemo(() => (edges || []).filter((e) => (e.type || 'reference') === 'reference'), [edges]);

  const addRef = () => {
    if (!selectedNode) return;
    if (!linkTo || linkTo === selectedNode.node_id) return;
    if (referenceEdges.some((e) => e.from === selectedNode.node_id && e.to === linkTo)) return;
    onSetEdges([...edges, { from: selectedNode.node_id, to: linkTo, reason: linkReason || '', type: 'reference' }]);
    onLinkReason('');
  };

  const removeRef = (edge: LogicEdge) => {
    onSetEdges(edges.filter((e) => !(e.from === edge.from && e.to === edge.to && (e.type || 'reference') === 'reference')));
  };

  return (
    <div className="flex-1 overflow-auto rounded-none border-none bg-transparent p-6 relative">
      <div className="flex items-center justify-between mb-6">
         <div className="text-lg font-bold text-slate-900 tracking-tight">Node Details</div>
         {onClose && (
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="h-4 w-4" /> 
            </button>
         )}
      </div>

      {!selectedNode ? (
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">Select a node to start editing.</div>
      ) : (
        <div className="mt-3 space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <div className="text-xs font-semibold text-slate-500">Title</div>
              <input
                value={draftTitle}
                onChange={(e) => onDraftTitle(e.target.value)}
                onBlur={onCommit}
                className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-3 text-sm outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-400"
              />
            </div>

            <div>
              <div className="text-xs font-semibold text-slate-500">Type</div>
              <select
                value={draftType}
                onChange={(e) => {
                  onDraftType(e.target.value as NodeType);
                }}
                onBlur={onCommit}
                className="mt-1 h-10 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-400"
              >
                <option value="section">section</option>
                <option value="subsection">subsection</option>
                <option value="content">content</option>
              </select>
            </div>

            <div>
              <div className="text-xs font-semibold text-slate-500">Duration (min)</div>
              <input
                type="number"
                min={1}
                value={draftMin}
                onChange={(e) => onDraftMin(Math.max(1, parseInt(e.target.value || '1', 10)))}
                onBlur={onCommit}
                className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-3 text-sm outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-400"
              />
            </div>

            <div className="sm:col-span-2">
              <div className="text-xs font-semibold text-slate-500">Summary</div>
              <textarea
                value={draftSummary}
                onChange={(e) => onDraftSummary(e.target.value)}
                onBlur={onCommit}
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-400"
                rows={5}
              />
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <Link2 className="h-4 w-4 text-slate-600" />
                Reference Links
              </div>
              <div className="text-xs font-semibold text-slate-500">{referenceEdges.length} total</div>
            </div>

            <div className="mt-3 space-y-2">
              {referenceEdges.length === 0 && <div className="text-sm text-slate-600">No reference links.</div>}
              {referenceEdges.map((e, idx) => (
                <div
                  key={`${e.from}-${e.to}-${idx}`}
                  className="flex items-start justify-between gap-3 rounded-lg bg-white border border-slate-200 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-slate-700">
                      {(idToTitle.get(e.from) || e.from) + ' → ' + (idToTitle.get(e.to) || e.to)}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">{e.reason || '—'}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeRef(e)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:text-rose-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <select
                value={linkTo}
                onChange={(e) => onLinkTo(e.target.value)}
                className="h-10 rounded-xl border border-slate-300 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-400"
              >
                {items
                  .filter((n) => n.node_id !== selectedNode.node_id)
                  .map((n) => (
                    <option key={n.node_id} value={n.node_id}>
                      {n.title}
                    </option>
                  ))}
              </select>
              <input
                value={linkReason}
                onChange={(e) => onLinkReason(e.target.value)}
                placeholder="Reason (optional)"
                className="h-10 rounded-xl border border-slate-300 px-3 text-sm outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-400 sm:col-span-2"
              />
              <button
                type="button"
                onClick={addRef}
                className="sm:col-span-3 inline-flex h-10 items-center justify-center rounded-xl bg-teal-600 text-sm font-semibold text-white hover:bg-teal-700 shadow-md transition-all duration-200"
              >
                Add Reference Link
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
