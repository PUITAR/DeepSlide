export interface TtsProgressCallbacks {
  onProgress?: (done: number, total: number) => void;
}

const apiBase = () => {
  const apiOrigin = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
  return apiOrigin ? `${apiOrigin}/api/v1` : '/api/v1';
};

export const generateTtsForPages = async (
  projectId: string,
  pageIndices: number[],
  { onProgress }: TtsProgressCallbacks = {}
): Promise<void> => {
  const total = pageIndices.length;
  if (total === 0) return;

  if (onProgress) onProgress(0, total);

  for (let i = 0; i < total; i += 1) {
    const pageIndex = pageIndices[i];
    try {
      const res = await fetch(`${apiBase()}/projects/${projectId}/tts/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_index: pageIndex }),
      });
      if (!res.ok) {
        try {
          const j = await res.json();
          const detail = String(j?.detail || '').toLowerCase();
          if (res.status === 400 && detail.includes('empty speech')) {
            if (onProgress) onProgress(i + 1, total);
            continue;
          }
          throw new Error(j?.detail || res.statusText || 'TTS generate failed');
        } catch (e) {
          if (e instanceof Error) throw e;
          throw new Error('TTS generate failed');
        }
      }
    } catch (err) {
      throw err;
    }
    if (onProgress) onProgress(i + 1, total);
  }
};
