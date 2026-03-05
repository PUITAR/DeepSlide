import client from './client';
import type { ChatMessage, ChatResponse, LogicEdge, LogicNode, Project, FileNode } from '../types';

export type CompileError = { message?: string; file?: string; line?: number | null };

export const getProjects = async (): Promise<Project[]> => {
  const response = await client.get<Project[]>('/projects/');
  return response.data;
};

export const getProject = async (projectId: string): Promise<Project> => {
  const response = await client.get<Project>(`/projects/${projectId}`);
  return response.data;
};

export const createProject = async (name: string): Promise<Project> => {
  const response = await client.post<Project>('/projects/', { name });
  return response.data;
};

export const createProjectWithUpload = async (name: string, file: File): Promise<Project> => {
  const formData = new FormData();
  formData.append('name', name);
  formData.append('file', file);
  
  const response = await client.post<Project>('/projects/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const createProjectWithPackageUpload = async (name: string, file: File): Promise<Project> => {
  const formData = new FormData();
  formData.append('name', name);
  formData.append('file', file);

  const response = await client.post<Project>('/projects/upload_package', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const getProjectFiles = async (projectId: string): Promise<FileNode[]> => {
  const response = await client.get<FileNode[]>(`/projects/${projectId}/files`);
  return response.data;
};

export const getFileContent = async (projectId: string, path: string): Promise<string> => {
  const response = await client.get<string>(`/projects/${projectId}/files/content`, {
    params: { path },
  });
  return response.data;
};

export const saveFileContent = async (projectId: string, path: string, content: string): Promise<void> => {
  await client.post(`/projects/${projectId}/files/content`, { path, content });
};

export const sendChatMessage = async (projectId: string, message: string): Promise<ChatResponse> => {
  const response = await client.post<ChatResponse>(`/projects/${projectId}/chat`, { message });
  return response.data;
};

export const getChatHistory = async (projectId: string): Promise<{history: ChatMessage[]}> => {
  const response = await client.get<{history: ChatMessage[]}>(`/projects/${projectId}/chat/history`);
  return response.data;
};

export const updateNodes = async (projectId: string, nodes: LogicNode[], edges?: LogicEdge[]): Promise<void> => {
  await client.post(`/projects/${projectId}/nodes`, { nodes, edges });
};

export const selectVoice = async (projectId: string, selected_voice_path: string): Promise<{success: boolean; selected_voice_path?: string}> => {
  const response = await client.post<{success: boolean; selected_voice_path?: string}>(`/projects/${projectId}/voice/select`, { selected_voice_path });
  return response.data;
};

export const recommendEdges = async (projectId: string, node_names: string[]): Promise<LogicEdge[]> => {
  const response = await client.post<LogicEdge[]>(`/projects/${projectId}/logic/recommend`, { node_names });
  return response.data;
};

export const selectLogicChainCandidate = async (projectId: string, candidate_id: string): Promise<Project> => {
  const response = await client.post<Project>(`/projects/${projectId}/logicchain/select`, { candidate_id });
  return response.data;
};

// --- Editor API ---

export const getEditorFiles = async (projectId: string): Promise<{files: Record<string, string>}> => {
  const response = await client.get<{files: Record<string, string>}>(`/projects/${projectId}/files`);
  return response.data;
};

export const saveEditorFiles = async (projectId: string, updates: Record<string, string>): Promise<void> => {
  await client.post(`/projects/${projectId}/save`, { updates });
};

export const compileProject = async (projectId: string): Promise<{success: boolean, errors: CompileError[]}> => {
  const response = await client.post<{success: boolean, errors: CompileError[]}>(`/projects/${projectId}/compile`);
  return response.data;
};

export const getPreviewPages = async (projectId: string): Promise<{pages: string[]}> => {
  const response = await client.get<{pages: string[]}>(`/projects/${projectId}/preview/pages`);
  return response.data;
};

export const aiBeautify = async (projectId: string, rounds: number): Promise<{success: boolean; compile?: {success: boolean; errors: any[]}}> => {
  const response = await client.post<{success: boolean; compile?: {success: boolean; errors: any[]}}>(`/projects/${projectId}/ai/beautify`, { rounds });
  return response.data;
};

export const aiGenerateHtml = async (
  projectId: string,
  focus_pages: number[],
  effects: string[],
  per_slide_max_regions: number,
  placement?: string,
  effects_by_page?: Record<string, string[]>,
  per_slide_max_regions_by_page?: Record<string, number>,
  visual_fx?: boolean,
  visual_fx_intensity?: 'low' | 'mid' | 'high',
  visual_fx_by_page?: Record<string, 'low' | 'mid' | 'high'>,
  visual_fx_enabled?: Record<string, boolean>
): Promise<{success: boolean; html?: string; meta?: any}> => {
  const response = await client.post<{success: boolean; html?: string; meta?: any}>(`/projects/${projectId}/ai/html/generate`, {
    focus_pages,
    effects,
    per_slide_max_regions,
    placement,
    effects_by_page,
    per_slide_max_regions_by_page,
    visual_fx,
    visual_fx_intensity,
    visual_fx_by_page,
    visual_fx_enabled,
    render_mode: 'spec',
    post_beautify: true,
  });
  return response.data;
};

export const getHtmlGenStatus = async (projectId: string): Promise<{status: string; current: number; total: number; error?: string}> => {
  const response = await client.get<{status: string; current: number; total: number; error?: string}>(`/projects/${projectId}/ai/html/status`);
  return response.data;
};

export const getHtmlPages = async (projectId: string): Promise<{pages: string[]; meta?: any}> => {
  const response = await client.get<{pages: string[]; meta?: any}>(`/projects/${projectId}/html/pages`);
  return response.data;
};



export const sendEditorCommand = async (projectId: string, command: string, pageIndex: number): Promise<{success: boolean}> => {
  const response = await client.post<{success: boolean}>(`/projects/${projectId}/command`, { command, page_index: pageIndex });
  return response.data;
};

export const startGenerateProjectSlides = async (projectId: string): Promise<{success: boolean; started: boolean; status?: string; current_index?: number; total?: number}> => {
  const response = await client.post<{success: boolean; started: boolean; status?: string; current_index?: number; total?: number}>(`/projects/${projectId}/generate`);
  return response.data;
};

export const getGenerateProjectSlidesStatus = async (projectId: string): Promise<{status: string; current_index?: number; current_title?: string; total?: number; compile?: any; error?: string}> => {
  const response = await client.get<{status: string; current_index?: number; current_title?: string; total?: number; compile?: any; error?: string}>(`/projects/${projectId}/generate/status`);
  return response.data;
};

export const getPreviewMetrics = async (projectId: string): Promise<any> => {
  const response = await client.get(`/projects/${projectId}/preview_insights/metrics`);
  return response.data;
};

export const getPreviewInsightsStatus = async (projectId: string): Promise<any> => {
  const response = await client.get(`/projects/${projectId}/preview_insights/status`, { timeout: 10000 });
  return response.data;
};

export const preparePreviewInsights = async (projectId: string, opts?: { include_llm?: boolean; force?: boolean }): Promise<any> => {
  const response = await client.post(`/projects/${projectId}/preview_insights/prepare`, {
    include_llm: opts?.include_llm ?? true,
    force: opts?.force ?? false,
    lang: 'en',
  }, { timeout: 10000 });
  return response.data;
};

export const getPreviewInsightsBundle = async (projectId: string): Promise<any> => {
  const response = await client.get(`/projects/${projectId}/preview_insights/bundle`, { timeout: 10000 });
  return response.data;
};

export const getPreviewCoach = async (projectId: string, pageIndex: number): Promise<{ok: boolean; page_index: number; advice: string[]; error?: string}> => {
  const response = await client.get<{ok: boolean; page_index: number; advice: string[]; error?: string}>(`/projects/${projectId}/preview_insights/coach`, { params: { page_index: pageIndex }, timeout: 10000 });
  return response.data;
};

export const regeneratePreviewCoach = async (projectId: string, pageIndex: number): Promise<{ok: boolean; page_index: number; advice: string[]}> => {
  const response = await client.post<{ok: boolean; page_index: number; advice: string[]}>(`/projects/${projectId}/preview_insights/coach/regenerate`, { page_index: pageIndex }, { timeout: 60000 });
  return response.data;
};

export const getPreviewQuestions = async (projectId: string, pageIndex: number): Promise<{ok: boolean; page_index: number; questions: string[]; error?: string}> => {
  const response = await client.get<{ok: boolean; page_index: number; questions: string[]; error?: string}>(`/projects/${projectId}/preview_insights/questions`, { params: { page_index: pageIndex }, timeout: 10000 });
  return response.data;
};

export const regeneratePreviewQuestions = async (projectId: string, pageIndex: number): Promise<{ok: boolean; page_index: number; questions: string[]}> => {
  const response = await client.post<{ok: boolean; page_index: number; questions: string[]}>(`/projects/${projectId}/preview_insights/questions/regenerate`, { page_index: pageIndex }, { timeout: 60000 });
  return response.data;
};
