import React, { useMemo, useState, useEffect } from 'react';
import { ArrowRight, Check } from 'lucide-react';
import { useProjectStore } from '../../store/useProjectStore';
import { LogicChainDetails } from '../logicChain/LogicChainDetails';
import { LogicChainCanvas } from '../logicChain/LogicChainCanvas';
import type { LogicEdge, LogicNode } from '../logicChain/types';
import type { NodeType } from '../logicChain/types';
import { parseDuration, toDuration } from '../logicChain/types';
import { AnimatePresence, motion } from 'framer-motion';
import { recommendEdges } from '../../api/projects';
import { StageNav } from '../StageNav';

const LogicChainView: React.FC = () => {
  const { currentProject, nodes, edges, updateProjectNodes, setEdges, isThinking, processingNodeId } = useProjectStore();
  
  // Initialize state from store, but also update when store changes (e.g. after chat)
  const [items, setItems] = useState<LogicNode[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');

  useEffect(() => {
    if (nodes && nodes.length > 0) {
        const normalized = nodes.map((n, i) => ({
            node_id: n.node_id || `node-${i}`,
            title: n.title || 'Untitled',
            summary: n.summary || n.content || '',
            node_type: (n.node_type as NodeType) || 'section',
            duration: n.duration || '5min',
        }));
        queueMicrotask(() => {
          setItems(normalized);
          if (!selectedId && normalized.length > 0) {
            setSelectedId('');
          }
        });
    }
  }, [nodes]);

  const selectedNode = useMemo(() => items.find((n) => n.node_id === selectedId) || null, [items, selectedId]);

  const [draftTitle, setDraftTitle] = useState<string>('');
  const [draftSummary, setDraftSummary] = useState<string>('');
  const [draftType, setDraftType] = useState<NodeType>('section');
  const [draftMin, setDraftMin] = useState<number>(5);
  const [linkTo, setLinkTo] = useState<string>('');
  const [linkReason, setLinkReason] = useState<string>('');

  const totalMin = useMemo(() => items.reduce((acc, n) => acc + parseDuration(n.duration), 0), [items]);

  // Sync draft when selection changes
  useEffect(() => {
    if (selectedNode) {
      queueMicrotask(() => {
        setDraftTitle(selectedNode.title || '');
        setDraftSummary(selectedNode.summary || '');
        setDraftType((selectedNode.node_type as NodeType) || 'section');
        setDraftMin(parseDuration(selectedNode.duration));
        setLinkTo(items.find((x) => x.node_id !== selectedId)?.node_id || '');
        setLinkReason('');
      });
    }
  }, [selectedId, items]); 

  const commitDraft = (base: LogicNode[]) => {
    if (!selectedNode) return base;
    const next = {
      ...selectedNode,
      title: draftTitle,
      summary: draftSummary,
      node_type: draftType,
      duration: toDuration(draftMin),
    };
    return base.map((n) => (n.node_id === next.node_id ? next : n));
  };

  const commitDraftInState = () => {
    setItems((prev) => commitDraft(prev));
  };

  const handleGenerateSlides = async () => {
    const nextItems = commitDraft(items);
    setItems(nextItems);
    try {
      await updateProjectNodes(nextItems, (edges as LogicEdge[]) || []);
    } catch (e) {
      console.error(e);
      alert('Generation failed. Please try again.');
    }
  };

  const onAutoConnect = async () => {
    if (!currentProject) return;
    try {
        const newEdgesRaw = await recommendEdges(currentProject.project_id, items.map(n => n.title));
        
        let newEdges: LogicEdge[] = [];
        const rawList: unknown[] = Array.isArray(newEdgesRaw) ? newEdgesRaw : [];
        if (rawList.length > 0) {
            newEdges = rawList
              .map((e): LogicEdge | null => {
                if (!e || typeof e !== 'object') return null;
                const obj = e as Record<string, unknown>;
                const fIdx = Number(obj.from);
                const tIdx = Number(obj.to);
                if (!Number.isFinite(fIdx) || !Number.isFinite(tIdx)) return null;
                if (fIdx >= 0 && fIdx < items.length && tIdx >= 0 && tIdx < items.length) {
                  return {
                    from: items[fIdx].node_id,
                    to: items[tIdx].node_id,
                    reason: typeof obj.reason === 'string' ? obj.reason : 'AI Recommended',
                    type: 'reference',
                  };
                }
                return null;
              })
              .filter((x): x is LogicEdge => x !== null);
        }

        // Fallback if empty or API failed to return valid edges
        if (newEdges.length === 0) {
             const n = items.length;
             if (n >= 3) {
                 for (let i = 0; i < n - 2; i++) {
                     newEdges.push({ 
                         from: items[i].node_id, 
                         to: items[i+2].node_id, 
                         type: 'reference', 
                         reason: 'Related' 
                     });
                 }
             }
        }
        
        // Merge: remove old reference edges, keep others (sequential?)
        // In v3 currently we only have 'reference' edges visible in overlay mostly, 
        // but sequential might be implicit or explicit.
        // Assuming we replace all reference edges.
        const nonRef = (edges as LogicEdge[] || []).filter(e => e.type !== 'reference');
        setEdges([...nonRef, ...newEdges]);
    } catch (e) {
        console.error("Auto connect failed", e);
        // Fallback on error
        const n = items.length;
        const fallbackEdges: LogicEdge[] = [];
        if (n >= 3) {
             for (let i = 0; i < n - 2; i++) {
                 fallbackEdges.push({ 
                     from: items[i].node_id, 
                     to: items[i+2].node_id, 
                     type: 'reference', 
                     reason: 'Related' 
                 });
             }
        }
        const nonRef = (edges as LogicEdge[] || []).filter(e => e.type !== 'reference');
        setEdges([...nonRef, ...fallbackEdges]);
    }
  };

  return (
    <div className="h-screen bg-transparent flex flex-col overflow-hidden font-sans">
      <StageNav
        title={currentProject?.name || "Logic Chain Editor"}
        rightContent={
          <div className="flex items-center gap-4">
            <div className="text-xs text-slate-500 font-medium hidden sm:block">
              {items.length} nodes · ~{totalMin} min
            </div>
            <button
              type="button"
              onClick={handleGenerateSlides}
              disabled={isThinking}
              className="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-4 py-2 text-xs font-bold text-white shadow-md shadow-teal-200 hover:shadow-teal-300 hover:bg-teal-700 hover:-translate-y-0.5 transition-all duration-200"
            >
              {isThinking ? (
                <>
                  <span className="inline-flex h-4 w-4 items-center justify-center">
                    <span className="h-3 w-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  </span>
                  <span>Generating…</span>
                </>
              ) : (
                <>
                  <Check className="h-3.5 w-3.5" />
                  <span>Confirm & Generate</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>
        }
      />

      <div className="flex-1 flex overflow-hidden relative">
        {/* Main Canvas */}
        <div className="flex-1 relative overflow-hidden bg-slate-50">
            <LogicChainCanvas
                nodes={items}
                edges={(edges as LogicEdge[]) || []}
                onNodesChange={setItems}
                onEdgesChange={setEdges}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onAutoConnect={onAutoConnect}
                processingNodeId={processingNodeId || undefined}
            />
        </div>

        {/* Right Panel - Floating & Glassmorphism */}
        <AnimatePresence>
          {selectedId && (
            <motion.div 
              initial={{ x: '100%', opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: '100%', opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="absolute right-0 top-0 bottom-0 w-96 border-l border-white/20 bg-white/90 z-30 shadow-2xl flex flex-col"
            >
                <LogicChainDetails
                    items={items}
                    selectedId={selectedId}
                    edges={(edges as LogicEdge[]) || []}
                    draftTitle={draftTitle}
                    draftSummary={draftSummary}
                    draftType={draftType}
                    draftMin={draftMin}
                    linkTo={linkTo}
                    linkReason={linkReason}
                    onDraftTitle={setDraftTitle}
                    onDraftSummary={setDraftSummary}
                    onDraftType={setDraftType}
                    onDraftMin={setDraftMin}
                    onLinkTo={setLinkTo}
                    onLinkReason={setLinkReason}
                    onCommit={commitDraftInState}
                    onSetEdges={setEdges}
                    onClose={() => setSelectedId('')} 
                />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default LogicChainView;
