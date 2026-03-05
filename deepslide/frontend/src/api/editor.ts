import client from './client';
import type { AIExecuteResponse, AIPlanResponse, AIPlanStep, CompileResponse } from '../types';

export const compileProject = async (projectId: string): Promise<CompileResponse> => {
  const response = await client.post<CompileResponse>(`/projects/${projectId}/compile`);
  return response.data;
};

export const getPreview = async (projectId: string): Promise<{images: string[]}> => {
  const response = await client.get<{images: string[]}>(`/projects/${projectId}/preview`);
  return response.data;
};

export const aiPlan = async (projectId: string, instruction: string, pageIdx: number, speeches: string[]): Promise<AIPlanResponse> => {
  const response = await client.post<AIPlanResponse>(`/projects/${projectId}/ai/plan`, {
    instruction,
    page_idx: pageIdx,
    speeches
  });
  return response.data;
};

export const aiExecute = async (
  projectId: string,
  plan: AIPlanStep[],
  pageIdx: number,
  speeches: string[]
): Promise<AIExecuteResponse> => {
  const response = await client.post<AIExecuteResponse>(`/projects/${projectId}/ai/execute`, {
    plan,
    page_idx: pageIdx,
    speeches
  });
  return response.data;
};
