import client from './client';

type AITextGenResponse = { result: string };

export const generateTitle = async (projectId: string, topic: string): Promise<AITextGenResponse> => {
  const response = await client.post<AITextGenResponse>(`/ai/title`, { project_id: projectId, topic });
  return response.data;
};

export const generateContent = async (projectId: string, sectionTitle: string): Promise<AITextGenResponse> => {
  const response = await client.post<AITextGenResponse>(`/ai/content`, { project_id: projectId, section_title: sectionTitle });
  return response.data;
};
