import React, { useState } from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { generateTitle, generateContent } from '../api/ai';
import { Sparkles, Loader2, Type, FileText } from 'lucide-react';

const AITools: React.FC = () => {
  const { currentProject, updateFileContent, fileContent } = useProjectStore();
  const [topic, setTopic] = useState('');
  const [sectionTitle, setSectionTitle] = useState('');
  const [loading, setLoading] = useState(false);

  const handleGenerateTitle = async () => {
    if (!currentProject || !topic) return;
    setLoading(true);
    try {
      const res = await generateTitle(currentProject.project_id, topic);
      // Append or replace? Let's append for now or replace if empty
      const newContent = fileContent ? `${fileContent}\n\n${res.result}` : res.result;
      updateFileContent(newContent);
    } catch (e) {
      console.error(e);
      alert('AI Generation Failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateContent = async () => {
    if (!currentProject || !sectionTitle) return;
    setLoading(true);
    try {
      const res = await generateContent(currentProject.project_id, sectionTitle);
      const newContent = fileContent ? `${fileContent}\n\n${res.result}` : res.result;
      updateFileContent(newContent);
    } catch (e) {
      console.error(e);
      alert('AI Generation Failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 space-y-6">
      <div className="space-y-3">
        <h3 className="font-medium flex items-center gap-2 text-gray-700">
          <Type size={16} />
          Generate Title & Outline
        </h3>
        <input
          className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          placeholder="Presentation Topic..."
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <button
          onClick={handleGenerateTitle}
          disabled={loading || !topic}
          className="w-full bg-purple-600 text-white py-2 rounded text-sm hover:bg-purple-700 disabled:opacity-50 flex justify-center items-center gap-2 transition-colors"
        >
          {loading ? <Loader2 className="animate-spin" size={14} /> : <Sparkles size={14} />}
          Generate
        </button>
      </div>

      <div className="border-t pt-6 space-y-3">
        <h3 className="font-medium flex items-center gap-2 text-gray-700">
          <FileText size={16} />
          Generate Section Content
        </h3>
        <input
          className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          placeholder="Section Title..."
          value={sectionTitle}
          onChange={(e) => setSectionTitle(e.target.value)}
        />
        <button
          onClick={handleGenerateContent}
          disabled={loading || !sectionTitle}
          className="w-full bg-purple-600 text-white py-2 rounded text-sm hover:bg-purple-700 disabled:opacity-50 flex justify-center items-center gap-2 transition-colors"
        >
          {loading ? <Loader2 className="animate-spin" size={14} /> : <Sparkles size={14} />}
          Generate
        </button>
      </div>
    </div>
  );
};

export default AITools;
