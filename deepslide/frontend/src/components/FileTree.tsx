import React from 'react';
import type { FileNode } from '../types';
import { useProjectStore } from '../store/useProjectStore';
import { Folder, FileText, ChevronRight, ChevronDown } from 'lucide-react';
import clsx from 'clsx';

interface FileTreeProps {
  nodes: FileNode[];
  projectId: string;
  level?: number;
}

const FileTree: React.FC<FileTreeProps> = ({ nodes, projectId, level = 0 }) => {
  const { selectFile, currentFile } = useProjectStore();
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});

  const toggleExpand = (path: string) => {
    setExpanded(prev => ({ ...prev, [path]: !prev[path] }));
  };

  return (
    <div className="text-sm select-none">
      {nodes.map((node) => {
        const isFolder = node.type === 'directory';
        const isExpanded = expanded[node.path];
        const isSelected = currentFile === node.path;
        
        return (
          <div key={node.path}>
            <div 
              className={clsx(
                "flex items-center py-1 px-2 cursor-pointer hover:bg-gray-100 transition-colors",
                isSelected && "bg-blue-50 text-blue-600 font-medium"
              )}
              style={{ paddingLeft: `${level * 12 + 8}px` }}
              onClick={() => {
                if (isFolder) toggleExpand(node.path);
                else selectFile(projectId, node.path);
              }}
            >
              <span className="mr-1 opacity-70 flex-shrink-0">
                {isFolder ? (
                   isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
                ) : <span className="w-3.5 inline-block" />}
              </span>
              <span className="mr-2 text-gray-500 flex-shrink-0">
                {isFolder ? <Folder size={16} /> : <FileText size={16} />}
              </span>
              <span className="truncate">{node.name}</span>
            </div>
            {isFolder && isExpanded && node.children && (
              <FileTree nodes={node.children} projectId={projectId} level={level + 1} />
            )}
          </div>
        );
      })}
    </div>
  );
};

export default FileTree;
