import React, { useState, useEffect } from 'react'
import FileUpload from './FileUpload'
import { Upload, Send, Eye, X, FileText } from 'lucide-react'

const MessageInput = ({ onSendMessage, isLoading, outputType, style, preSelectedFiles, onPreSelectedFilesClear, hasMessages = false }) => {
  const [selectedFiles, setSelectedFiles] = useState([])
  const [previewFile, setPreviewFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [isDragging, setIsDragging] = useState(false)

  // Handle pre-selected files from sidebar
  useEffect(() => {
    if (preSelectedFiles && preSelectedFiles.length > 0) {
      setSelectedFiles(prev => {
        // Avoid duplicates
        const existingNames = new Set(prev.map(f => f.name))
        const newFiles = preSelectedFiles.filter(f => !existingNames.has(f.name))
        return [...prev, ...newFiles]
      })
      // Clear pre-selected files after adding them
      if (onPreSelectedFilesClear) {
        onPreSelectedFilesClear()
      }
    }
  }, [preSelectedFiles, onPreSelectedFilesClear])

  // Cleanup preview URL on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (selectedFiles.length > 0) {
      onSendMessage('', selectedFiles)
      setSelectedFiles([])
    }
  }

  const handleFilesSelected = (files) => {
    setSelectedFiles(prev => [...prev, ...files])
  }

  const removeFile = (index) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const openPreview = (file) => {
    setPreviewFile(file)
    // Create blob URL for PDF preview
    if (file.type === 'application/pdf' && file instanceof File) {
      const url = URL.createObjectURL(file)
      setPreviewUrl(url)
    } else {
      setPreviewUrl(null)
    }
  }

  const closePreview = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }
    setPreviewFile(null)
    setPreviewUrl(null)
  }

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown size'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const getFileTypeName = (file) => {
    const ext = file.name?.split('.').pop()?.toLowerCase()
    if (ext === 'pdf') return 'PDF Document'
    if (ext === 'md' || ext === 'markdown') return 'Markdown'
    if (ext === 'doc') return 'Word Document'
    if (ext === 'docx') return 'Word Document'
    if (ext === 'ppt' || ext === 'pptx') return 'PowerPoint'
    return file.type || 'Document'
  }

  const canSend = selectedFiles.length > 0

  // Drag and drop handlers
  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      handleFilesSelected(files)
    }
  }

  return (
    <div className="bg-white dark:bg-gray-900">
      {/* Upload and Send Area - Only show when no messages exist */}
      {!hasMessages && (
      <div className="w-full px-6 py-4">
        <div 
          className={`relative border-2 border-dashed rounded-2xl px-6 py-4 transition-all ${
            isDragging 
              ? 'border-purple-400 bg-purple-50 dark:bg-purple-900/20' 
              : 'border-gray-300 dark:border-gray-700 hover:border-purple-300 dark:hover:border-purple-600'
          }`}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex items-center justify-between gap-4">
              {/* Upload Area - Clickable */}
              <FileUpload
                onFilesSelected={handleFilesSelected}
                disabled={isLoading}
                customButton={(onClick) => (
                  <button
                    type="button"
                    onClick={onClick}
                    disabled={isLoading}
                    className="flex items-center gap-4 flex-1 text-left disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-80 transition-opacity"
                  >
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-100 to-pink-100 dark:from-purple-900/30 dark:to-pink-900/30 flex items-center justify-center flex-shrink-0">
                      <Upload className="w-6 h-6 text-purple-600 dark:text-purple-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {selectedFiles.length > 0 ? `${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''} selected` : 'Drop files here or click to upload'}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        PDF, DOC, DOCX, Markdown
                      </p>
                    </div>
                  </button>
                )}
              />
              
              {/* Generate Button */}
              <button
                type="submit"
                disabled={isLoading || !canSend}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all shadow-md hover:shadow-lg disabled:cursor-not-allowed flex-shrink-0 ${
                  canSend && !isLoading
                    ? 'bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-800 text-gray-400'
                }`}
                title="Generate"
              >
                {isLoading ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                    <span>Generating...</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <Send className="w-4 h-4" />
                    <span>Generate</span>
                  </div>
                )}
              </button>
            </div>
            
            {/* Selected Files List - Compact */}
            {selectedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                {selectedFiles.map((file, index) => (
                  <div
                    key={index}
                    className="group flex items-center gap-2 px-3 py-1.5 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-700 rounded-lg text-xs"
                  >
                    <FileText className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 flex-shrink-0" />
                    <span className="text-gray-900 dark:text-gray-100 truncate max-w-[150px]" title={file.name}>
                      {file.name}
                    </span>
                    <div className="flex items-center gap-1 ml-1">
                      <button
                        type="button"
                        onClick={() => openPreview(file)}
                        className="w-5 h-5 flex items-center justify-center rounded hover:bg-purple-100 dark:hover:bg-purple-900/30 text-gray-500 dark:text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Preview"
                      >
                        <Eye className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="w-5 h-5 flex items-center justify-center rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-500 dark:text-gray-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Remove"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </form>
        </div>
      </div>
      )}

      {/* File Preview Modal */}
      {previewFile && (
        <div 
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
          onClick={closePreview}
        >
          <div 
            className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center gap-4 px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 via-pink-500 to-purple-600 flex items-center justify-center shadow-lg">
                <FileText className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
                  {previewFile.name}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {formatFileSize(previewFile.size)} • {getFileTypeName(previewFile)}
                </p>
              </div>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-auto p-6">
              {previewUrl && previewFile.type === 'application/pdf' ? (
                <iframe
                  src={previewUrl}
                  className="w-full h-[60vh] rounded-lg border border-gray-200 dark:border-gray-700"
                  title="PDF Preview"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-[40vh] text-center">
                  <div className="w-28 h-28 rounded-3xl bg-gradient-to-br from-purple-500 via-pink-500 to-purple-600 flex items-center justify-center mb-6 shadow-xl">
                    <FileText className="w-14 h-14 text-white" />
                  </div>
                  <h4 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    {previewFile.name}
                  </h4>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                    Preview not available for this file type
                  </p>
                  <div className="flex gap-6 text-sm">
                    <div className="px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
                      <span className="text-gray-500 dark:text-gray-400">Size</span>
                      <p className="font-medium text-gray-900 dark:text-gray-100">{formatFileSize(previewFile.size)}</p>
                    </div>
                    <div className="px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
                      <span className="text-gray-500 dark:text-gray-400">Type</span>
                      <p className="font-medium text-gray-900 dark:text-gray-100">{getFileTypeName(previewFile)}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
              <button
                onClick={closePreview}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-medium transition-all"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MessageInput
