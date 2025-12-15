import React, { useState } from 'react'
import { FileText, Download, File, ChevronDown, ChevronRight, Presentation, Image as ImageIcon } from 'lucide-react'

const HistoryPanel = ({ history, uploadedDocuments, onSelectFile, onSelectHistoryItem }) => {
  const [expandedItems, setExpandedItems] = useState({})
  const [activeTab, setActiveTab] = useState('history') // 'history' or 'documents'

  const toggleExpand = (id) => {
    setExpandedItems(prev => ({
      ...prev,
      [id]: !prev[id]
    }))
  }

  const formatDate = (date) => {
    if (!date) return ''
    const d = new Date(date)
    const now = new Date()
    const diff = now - d
    
    if (diff < 60000) return 'Just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`
    
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  // Generate display name for history item
  const getHistoryItemDisplayName = (item) => {
    // Format: Slides/Poster - FileName - style - content - length/density
    const parts = []
    
    // Output type
    parts.push(item.outputType === 'slides' || item.outputType === 'ppt' ? 'Slides' : 'Poster')
    
    // Source file name (without extension)
    if (item.sourceFiles && item.sourceFiles.length > 0) {
      const firstFileName = item.sourceFiles[0].name || item.sourceFiles[0].filename || item.sourceFiles[0]
      const cleanName = typeof firstFileName === 'string' ? firstFileName.replace(/\.[^/.]+$/, '') : 'file'
      parts.push(cleanName)
    }
    
    // Style
    if (item.style) {
      parts.push(item.style)
    }
    
    // Content
    if (item.content) {
      parts.push(item.content)
    }
    
    // Length or Density
    if (item.outputType === 'slides' && item.length) {
      parts.push(item.length)
    } else if (item.outputType === 'poster' && item.density) {
      parts.push(item.density)
    }
    
    return parts.join(' - ')
  }

  const handleFileClick = (file, e) => {
    e?.stopPropagation()
    if (onSelectFile) {
      onSelectFile(file)
    }
  }

  const handleHistoryItemClick = (item) => {
    if (onSelectHistoryItem) {
      onSelectHistoryItem(item)
    }
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900 rounded-2xl shadow-xl overflow-hidden">
      {/* Header - Fixed height for alignment */}
      <div className="flex items-center justify-between px-6 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 h-[72px] flex-shrink-0">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          History & Documents
        </h2>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900">
        <button
          onClick={() => setActiveTab('history')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center ${
            activeTab === 'history'
              ? 'text-purple-600 dark:text-purple-400 border-b-2 border-purple-500 bg-purple-50 dark:bg-purple-900/20'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          Generated Files
        </button>
        <button
          onClick={() => setActiveTab('documents')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center ${
            activeTab === 'documents'
              ? 'text-purple-600 dark:text-purple-400 border-b-2 border-purple-500 bg-purple-50 dark:bg-purple-900/20'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          Documents
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'history' ? (
          <div className="p-3">
            {history.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">
                No generated files yet
              </div>
            ) : (
              <div className="space-y-2">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden hover:border-blue-300 dark:hover:border-blue-700 transition-colors cursor-pointer"
                    onClick={() => handleHistoryItemClick(item)}
                  >
                    {/* Main Item Header */}
                    <div className="px-3 py-2.5 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 flex-1 min-w-0">
                          {item.outputType === 'slides' || item.outputType === 'ppt' ? (
                            <Presentation className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                          ) : (
                            <ImageIcon className="w-4 h-4 text-purple-600 dark:text-purple-400 flex-shrink-0 mt-0.5" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                              {getHistoryItemDisplayName(item)}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                              {formatDate(item.timestamp)}
                            </div>
                          </div>
                        </div>
                        {(item.pptUrl || item.posterUrl) && (
                          <a
                            href={item.pptUrl || item.posterUrl}
                            download
                            onClick={(e) => e.stopPropagation()}
                            className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors flex-shrink-0"
                            title="Download"
                          >
                            <Download className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                          </a>
                        )}
                      </div>
                    </div>

                    {/* Source Files */}
                    {item.sourceFiles && item.sourceFiles.length > 0 && (
                      <div className="px-3 py-2 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleExpand(item.id)
                          }}
                          className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 mb-2"
                        >
                          {expandedItems[item.id] ? (
                            <ChevronDown className="w-3 h-3" />
                          ) : (
                            <ChevronRight className="w-3 h-3" />
                          )}
                          <span>Source Files ({item.sourceFiles.length})</span>
                        </button>
                        {expandedItems[item.id] && (
                          <div className="space-y-1 mt-2">
                            {item.sourceFiles.map((file, index) => (
                              <button
                                key={index}
                                onClick={(e) => handleFileClick(file, e)}
                                className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-left group"
                                title="Click to reuse this file"
                              >
                                <File className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 group-hover:text-blue-600 dark:group-hover:text-blue-400 flex-shrink-0" />
                                <span className="text-xs text-gray-700 dark:text-gray-300 truncate flex-1">
                                  {file.name || file.filename}
                                </span>
                                {file.size && (
                                  <span className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
                                    ({(file.size / 1024).toFixed(1)} KB)
                                  </span>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="p-3">
            {uploadedDocuments.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">
                No documents uploaded yet
              </div>
            ) : (
              <div className="space-y-2">
                {uploadedDocuments.map((doc, index) => (
                  <button
                    key={index}
                    onClick={() => handleFileClick(doc)}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-left group"
                  >
                    <FileText className="w-4 h-4 text-gray-400 dark:text-gray-500 group-hover:text-blue-600 dark:group-hover:text-blue-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                        {doc.name || doc.filename}
                      </div>
                      {doc.size && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          {(doc.size / 1024).toFixed(1)} KB
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default HistoryPanel

