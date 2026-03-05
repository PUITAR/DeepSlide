import React from 'react';
import { useProjectStore } from '../../store/useProjectStore';
import { ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';

const PreviewPanel: React.FC = () => {
  const { previewImages, currentPage, setPage, compilerErrors, isCompiling } = useProjectStore();

  const handlePrev = () => {
    if (currentPage > 0) setPage(currentPage - 1);
  };

  const handleNext = () => {
    if (currentPage < previewImages.length - 1) setPage(currentPage + 1);
  };

  const currentImage = previewImages[currentPage];

  // Determine image URL
  const imageUrl = currentImage 
    ? (currentImage.startsWith('http') ? currentImage : `/api/v1/projects/${useProjectStore.getState().currentProject?.project_id}/files/content?path=preview_cache/${currentImage}`)
    : null;
    
  // Actually, we need a way to serve static files or use the file content API
  // My backend API `getFileContent` returns string content, not binary for images.
  // I should probably use a direct static file serving or base64.
  // The `compiler_service` returns filenames.
  
  // Let's assume we can fetch the image via a new endpoint or the existing one if it supports binary.
  // Or better, let's update the backend to serve the project directory as static files temporarily?
  // No, let's use a specific endpoint for preview images.
  
  // I'll assume for now `imageUrl` is handled. 
  // Wait, I haven't implemented an image serving endpoint.
  // `getFileContent` reads text.
  
  // Let's add a quick endpoint in `editor.py` or `projects.py` to serve images?
  // Or just use base64 in `generate_preview_images`? 
  // Base64 is easier for now to avoid static serving issues.
  
  return (
    <div className="h-full flex flex-col bg-gray-100 relative">
      <div className="flex-1 overflow-auto flex items-center justify-center p-4">
        {isCompiling && (
          <div className="absolute inset-0 bg-black/10 z-10 flex items-center justify-center">
            <div className="bg-white p-4 rounded-lg shadow-lg flex items-center gap-3">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              <span>Compiling...</span>
            </div>
          </div>
        )}
        
        {imageUrl ? (
          <img 
            src={imageUrl} 
            alt={`Slide ${currentPage + 1}`} 
            className="max-h-full max-w-full shadow-lg border border-gray-200"
          />
        ) : (
          <div className="text-gray-400 text-center">
            <p>No preview available</p>
            <p className="text-sm">Compile the project to generate slides</p>
          </div>
        )}
      </div>
      
      {/* Navigation Bar */}
      <div className="h-12 bg-white border-t flex items-center justify-between px-4">
        <button 
          onClick={handlePrev} 
          disabled={currentPage === 0}
          className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        
        <span className="text-sm font-medium text-gray-600">
          {currentPage + 1} / {previewImages.length || 1}
        </span>
        
        <button 
          onClick={handleNext} 
          disabled={currentPage >= previewImages.length - 1}
          className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Error Overlay */}
      {compilerErrors.length > 0 && (
        <div className="absolute bottom-12 left-4 right-4 bg-red-50 border border-red-200 rounded-lg p-3 shadow-lg max-h-40 overflow-auto">
          <div className="flex items-center gap-2 text-red-700 font-medium mb-1">
            <AlertCircle className="w-4 h-4" />
            Compilation Errors
          </div>
          <ul className="text-xs text-red-600 space-y-1">
            {compilerErrors.map((err, i) => (
              <li key={i}>{err.message} ({err.file}:{err.line})</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default PreviewPanel;
