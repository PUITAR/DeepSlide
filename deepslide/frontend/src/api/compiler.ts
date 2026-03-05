import client from './client';
import type { CompileResponse } from '../types';

export const compileProject = async (projectId: string): Promise<CompileResponse> => {
  const response = await client.post<CompileResponse>(`/compile/${projectId}`);
  return response.data;
};
