import React, { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useProjectStore } from '../store/useProjectStore';
import { getProjects } from '../api/projects';
import FileTree from '../components/FileTree';
import PreviewPanel from '../components/preview/PreviewPanel';
import EditorPanel from '../components/editor/EditorPanel';
import ChatInput from '../components/input/ChatInput';
import { Loader2 } from 'lucide-react';

const Workspace: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const { 
    currentProject, 
    setCurrentProject, 
    loadFiles, 
    isLoadingFiles,
    files
  } = useProjectStore();

  useEffect(() => {
    const init = async () => {
      if (projectId) {
        // Find or fetch project
        // Simple fetch all for now, in real app fetch specific
        const projects = await getProjects();
        const p = projects.find(p => p.project_id === projectId);
        if (p) {
          setCurrentProject(p);
          loadFiles(projectId);
        }
      }
    };
    init();
  }, [projectId]);

  if (!currentProject) {
    return <div className="flex justify-center items-center h-screen"><Loader2 className="animate-spin" /></div>;
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="h-12 bg-white border-b flex items-center px-4 justify-between">
        <div className="flex items-center gap-2">
          <span className="font-bold text-lg bg-gradient-to-r from-blue-600 to-purple-600 text-transparent bg-clip-text">
            DeepSlide
          </span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-medium text-gray-600">{currentProject.name}</span>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Preview (60%) */}
        <div className="w-[60%] flex flex-col border-r relative">
          <PreviewPanel />
          <ChatInput />
        </div>

        {/* Right: Editor & Files (40%) */}
        <div className="w-[40%] flex flex-col bg-white">
          <div className="flex-1 flex flex-col">
             {/* Simple Tabs: Files | Editor */}
             <div className="flex-1 flex flex-col">
                <div className="h-1/3 border-b overflow-auto">
                    <div className="p-2 bg-gray-50 text-xs font-semibold text-gray-500 uppercase">Files</div>
                    {isLoadingFiles ? (
                      <div className="p-4"><Loader2 className="w-4 h-4 animate-spin"/></div>
                    ) : (
                      <FileTree nodes={files} projectId={currentProject.project_id} />
                    )}
                </div>
                <div className="flex-1 flex flex-col">
                    <EditorPanel />
                </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Workspace;
