export type NodeType = 'section' | 'subsection' | 'content';

export type LogicNode = {
  node_id: string;
  title: string;
  summary?: string;
  node_type?: NodeType;
  duration?: string;
};

export type LogicEdge = {
  from: string;
  to: string;
  reason?: string;
  type?: string;
};

export const parseDuration = (s: string | undefined): number => {
  if (!s) return 5;
  const m = s.match(/(\d+)/);
  return m ? Math.max(1, parseInt(m[1], 10)) : 5;
};

export const toDuration = (min: number): string => `${Math.max(1, Math.round(min))}min`;

