import React, { useState, useEffect } from 'react';
import { useProjectStore } from '../../store/useProjectStore';
import { Save, RefreshCw } from 'lucide-react';

const EditorPanel: React.FC = () => {
  const { 
    currentFile, 
    fileContent, 
    updateFileContent, 
    saveCurrentFile,
    isCompiling,
    compile
  } = useProjectStore();

  const [localContent, setLocalContent] = useState('');

  useEffect(() => {
    setLocalContent(fileContent);
  }, [fileContent]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setLocalContent(e.target.value);
    updateFileContent(e.target.value);
  };

  const handleSave = async () => {
    await saveCurrentFile();
  };

  if (!currentFile) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        Select a file to edit
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white border-l">
      {/* Toolbar */}
      <div className="h-10 border-b flex items-center justify-between px-4 bg-gray-50">
        <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]">
          {currentFile}
        </span>
        <div className="flex items-center gap-2">
          <button 
            onClick={handleSave}
            className="p-1.5 hover:bg-gray-200 rounded text-gray-600"
            title="Save (Ctrl+S)"
          >
            <Save className="w-4 h-4" />
          </button>
          <button 
            onClick={compile}
            disabled={isCompiling}
            className={`p-1.5 hover:bg-gray-200 rounded text-blue-600 ${isCompiling ? 'animate-spin' : ''}`}
            title="Compile"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      {/* Editor Area */}
      <textarea
        className="flex-1 w-full p-4 font-mono text-sm resize-none focus:outline-none"
        value={localContent}
        onChange={handleChange}
        spellCheck={false}
      />
    </div>
  );
};

export default EditorPanel;
