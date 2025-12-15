import React, { useState, useEffect } from 'react'
import { FileText, Download, ChevronDown, ChevronRight, File } from 'lucide-react'

const Sidebar = ({ history, onSelectFile, onClose }) => {
  const [expandedItems, setExpandedItems] = useState({})
  const [allFiles, setAllFiles] = useState([])

  // Extract all unique files from history
  useEffect(() => {
    const files = []
    const fileMap = new Map()

    history.forEach(item => {
      item.sourceFiles?.forEach(file => {
        // Use file name as key to avoid duplicates
        const key = file.name || file.filename
        if (!fileMap.has(key)) {
          fileMap.set(key, {
            ...file,
            usedIn: [item.id]
          })
        } else {
          fileMap.get(key).usedIn.push(item.id)
        }
      })
    })

    setAllFiles(Array.from(fileMap.values()))
  }, [history])

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

  const handleFileClick = (file) => {
    if (onSelectFile) {
      // Create a File object from the stored file info
      // Note: This is a simplified approach. In production, you might need to fetch the actual file
      onSelectFile(file)
    }
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Sidebar Header - Aligned with main header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200/50 dark:border-gray-800/50 bg-[#faf9f6] dark:bg-[#171717] h-[52px]">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Generated Files
        </h2>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto">
        {history.length === 0 ? (
          <div className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">
            No generated files yet
          </div>
        ) : (
          <div className="p-2">
            {history.map((item) => (
              <div
                key={item.id}
                className="mb-2 border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden"
              >
                {/* Main Item Header */}
                <div
                  className="px-3 py-2 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                  onClick={() => toggleExpand(item.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      {item.sourceFiles && item.sourceFiles.length > 0 ? (
                        <button
                          className="flex-shrink-0 text-gray-400 dark:text-gray-500"
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleExpand(item.id)
                          }}
                        >
                          {expandedItems[item.id] ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </button>
                      ) : null}
                      <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                          {item.outputType === 'ppt' ? 'PPT' : 'Poster'} - {item.style}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
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

                {/* Expanded Source Files */}
                {expandedItems[item.id] && item.sourceFiles && item.sourceFiles.length > 0 && (
                  <div className="px-3 py-2 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800">
                    <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Source Files:
                    </div>
                    <div className="space-y-1">
                      {item.sourceFiles.map((file, index) => (
                        <button
                          key={index}
                          onClick={() => handleFileClick(file)}
                          className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-left group"
                          title="Click to reuse this file"
                        >
                          <File className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 group-hover:text-blue-600 dark:group-hover:text-blue-400 flex-shrink-0" />
                          <span className="text-xs text-gray-700 dark:text-gray-300 truncate flex-1">
                            {file.name || file.filename}
                          </span>
                          <span className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
                            {file.size ? `(${(file.size / 1024).toFixed(1)} KB)` : ''}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* All Files Index Section */}
        {allFiles.length > 0 && (
          <div className="border-t border-gray-200 dark:border-gray-800 mt-4">
            <div className="px-4 py-2 bg-gray-50 dark:bg-gray-800/50">
              <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                File Index
              </h3>
            </div>
            <div className="p-2 space-y-1">
              {allFiles.map((file, index) => (
                <button
                  key={index}
                  onClick={() => handleFileClick(file)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-left group"
                  title={`Used in ${file.usedIn.length} generation(s). Click to reuse.`}
                >
                  <File className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 group-hover:text-blue-600 dark:group-hover:text-blue-400 flex-shrink-0" />
                  <span className="text-xs text-gray-700 dark:text-gray-300 truncate flex-1">
                    {file.name || file.filename}
                  </span>
                  {file.usedIn.length > 1 && (
                    <span className="text-xs text-blue-600 dark:text-blue-400 flex-shrink-0">
                      {file.usedIn.length}x
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Sidebar

