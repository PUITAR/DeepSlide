export type ChatMessage = { role: 'user' | 'assistant'; content: string };

export type Requirements = {
  audience?: string;
  duration?: string;
  focus_sections?: string[];
  style_preference?: string;
};

export type Analysis = {
  main_file?: string;
  base_dir?: string;
  abstract?: string;
  nodes?: unknown[];
  feedback?: unknown;
};

export type LogicNode = {
  node_id: string;
  title: string;
  summary?: string;
  content?: string;
  node_type?: string;
  duration?: string;
  metadata?: unknown;
};

export type LogicEdge = {
  from: string;
  to: string;
  reason?: string;
  type?: string;
};

export interface Project {
  project_id: string;
  name: string;
  created_at: string;
  path: string;
  nodes?: LogicNode[];
  edges?: LogicEdge[];
  requirements?: Requirements;
  is_confirmed?: boolean;
  analysis?: Analysis;
  voice_prompt_path?: string;
  selected_voice_path?: string;
}

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
}

export interface CompileResponse {
  success: boolean;
  errors: Array<{message: string, file: string, line: number | null}>;
  preview_images: string[];
}

export type AIPlanStep = { action: string; instruction: string };

export type AIPlanResponse = { plan: AIPlanStep[] };

export type AIExecuteResponse = { success: boolean; speeches?: string[] };

export interface ChatResponse {
  response: string;
  history: ChatMessage[];
  is_confirmed: boolean;
  requirements: Requirements;
  logic_chain_candidates?: Array<{
    candidate_id: string;
    title: string;
    reason?: string;
    nodes: LogicNode[];
    edges: LogicEdge[];
  }>;
}
