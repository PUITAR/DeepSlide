import React, { useEffect } from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { Save, Loader2 } from 'lucide-react';

const Editor: React.FC = () => {
  const { currentFile, fileContent, updateFileContent, saveCurrentFile } = useProjectStore();
  const [isSaving, setIsSaving] = React.useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    await saveCurrentFile();
    setIsSaving(false);
  };

  // Keyboard shortcut for save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [saveCurrentFile]);

  if (!currentFile) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 bg-gray-50 h-full">
        Select a file to edit
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full border-r bg-white min-w-0">
      <div className="h-10 border-b flex items-center justify-between px-4 bg-gray-50 flex-shrink-0">
        <span className="text-sm font-medium text-gray-600 truncate">{currentFile}</span>
        <button 
          onClick={handleSave}
          disabled={isSaving}
          className="p-1 hover:bg-gray-200 rounded text-gray-600 transition-colors"
          title="Save (Ctrl+S)"
        >
          {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        </button>
      </div>
      <textarea
        className="flex-1 w-full p-4 font-mono text-sm resize-none focus:outline-none"
        value={fileContent}
        onChange={(e) => updateFileContent(e.target.value)}
        spellCheck={false}
      />
    </div>
  );
};

export default Editor;
