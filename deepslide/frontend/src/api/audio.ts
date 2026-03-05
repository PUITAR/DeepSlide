import client from './client';

export const transcribeAudio = async (
  projectId: string, 
  audio: Blob, 
  lang?: string,
  saveVoice?: boolean
): Promise<{ text: string; voice_cloned?: boolean; voice_path?: string }> => {
  const formData = new FormData();
  formData.append('audio', audio, 'recording.webm');
  if (lang) formData.append('lang', lang);
  if (saveVoice) formData.append('save_voice', 'true');

  const response = await client.post<{ text: string; voice_cloned?: boolean; voice_path?: string }>(
    `/projects/${projectId}/audio/transcribe`, 
    formData, 
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return response.data;
};
