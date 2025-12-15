import React, { useState } from 'react'
import { Plus, MessageSquare, FileText, Trash2, MoreHorizontal, PanelLeftClose, X, AlertCircle } from 'lucide-react'

const ConversationList = ({ 
  conversations, 
  currentConversationId, 
  onSelectConversation, 
  onNewConversation, 
  onDeleteConversation,
  onCollapse
}) => {
  const [showMenuId, setShowMenuId] = useState(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState(null)

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

  const getConversationTitle = (conv) => {
    // Use first file name as title, or default
    if (conv.files && conv.files.length > 0) {
      const fileName = conv.files[0].name || conv.files[0].filename
      // Remove extension and truncate
      const baseName = fileName.replace(/\.[^/.]+$/, '')
      return baseName.length > 30 ? baseName.slice(0, 30) + '...' : baseName
    }
    return conv.title || 'New Chat'
  }

  const getConversationSubtitle = (conv) => {
    const fileCount = conv.files?.length || 0
    const messageCount = conv.messages?.length || 0
    const parts = []
    
    if (fileCount > 0) {
      parts.push(`${fileCount} file${fileCount > 1 ? 's' : ''}`)
    }
    if (messageCount > 0) {
      parts.push(`${messageCount} message${messageCount > 1 ? 's' : ''}`)
    }
    
    return parts.length > 0 ? parts.join(' · ') : 'Empty'
  }

  const handleDeleteClick = (e, convId) => {
    e.stopPropagation()
    setShowMenuId(null)
    setDeleteConfirmId(convId)
  }

  const handleConfirmDelete = (e) => {
    e.stopPropagation()
    if (deleteConfirmId && onDeleteConversation) {
      onDeleteConversation(deleteConfirmId)
    }
    setDeleteConfirmId(null)
  }

  const handleCancelDelete = (e) => {
    e.stopPropagation()
    setDeleteConfirmId(null)
  }

  const toggleMenu = (e, convId) => {
    e.stopPropagation()
    setShowMenuId(showMenuId === convId ? null : convId)
  }

  // Group conversations by date
  const groupByDate = (convs) => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    const weekAgo = new Date(today)
    weekAgo.setDate(weekAgo.getDate() - 7)

    const groups = {
      today: [],
      yesterday: [],
      thisWeek: [],
      older: []
    }

    convs.forEach(conv => {
      const date = new Date(conv.updatedAt || conv.createdAt)
      date.setHours(0, 0, 0, 0)
      
      if (date.getTime() === today.getTime()) {
        groups.today.push(conv)
      } else if (date.getTime() === yesterday.getTime()) {
        groups.yesterday.push(conv)
      } else if (date > weekAgo) {
        groups.thisWeek.push(conv)
      } else {
        groups.older.push(conv)
      }
    })

    return groups
  }

  const groups = groupByDate(conversations)

  const renderGroup = (title, convs) => {
    if (convs.length === 0) return null

    return (
      <div className="mb-4">
        <h3 className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {title}
        </h3>
        <div className="space-y-1">
          {convs.map((conv) => (
            <div
              key={conv.id}
              className={`group relative mx-2 rounded-xl cursor-pointer transition-all duration-300 ease-in-out ${
                currentConversationId === conv.id
                  ? 'bg-gradient-to-r from-purple-100 to-pink-100 dark:from-purple-900/40 dark:to-pink-900/40 border-2 border-purple-300 dark:border-purple-600 shadow-md'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-800 border-2 border-transparent'
              }`}
              onClick={() => onSelectConversation(conv.id)}
            >
              <div className="flex items-start gap-3 p-3">
                {/* Icon - Always show conversation icon */}
                <div className={`flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${
                  currentConversationId === conv.id
                    ? 'bg-gradient-to-br from-purple-500 to-pink-500'
                    : 'bg-gray-200 dark:bg-gray-700'
                }`}>
                  <MessageSquare className={`w-4 h-4 ${
                    currentConversationId === conv.id ? 'text-white' : 'text-gray-500 dark:text-gray-400'
                  }`} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-medium truncate ${
                    currentConversationId === conv.id
                      ? 'text-purple-900 dark:text-purple-100'
                      : 'text-gray-900 dark:text-gray-100'
                  }`}>
                    {getConversationTitle(conv)}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
                    {getConversationSubtitle(conv)}
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {formatDate(conv.updatedAt || conv.createdAt)}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => toggleMenu(e, conv.id)}
                    className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
                  >
                    <MoreHorizontal className="w-4 h-4" />
                  </button>
                </div>

                {/* Dropdown Menu */}
                {showMenuId === conv.id && (
                  <div 
                    className="absolute right-2 top-full mt-1 z-10 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 min-w-[120px]"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={(e) => handleDeleteClick(e, conv.id)}
                      className="w-full px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 flex items-center gap-2"
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900 rounded-2xl shadow-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 flex-shrink-0">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Conversations
        </h2>
        <button
          onClick={onCollapse}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          title="Collapse sidebar"
        >
          <PanelLeftClose className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto py-2" onClick={() => setShowMenuId(null)}>
        {conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-100 to-pink-100 dark:from-purple-900/30 dark:to-pink-900/30 flex items-center justify-center mb-4">
              <MessageSquare className="w-8 h-8 text-purple-500 dark:text-purple-400" />
            </div>
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100 mb-2">
              No conversations yet
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Click the button below to start a new conversation
            </p>
          </div>
        ) : (
          <>
            {renderGroup('Today', groups.today)}
            {renderGroup('Yesterday', groups.yesterday)}
            {renderGroup('This Week', groups.thisWeek)}
            {renderGroup('Older', groups.older)}
          </>
        )}
      </div>

      {/* New Conversation Button - Bottom */}
      <div className="p-3 border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 flex-shrink-0">
        <button
          onClick={onNewConversation}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-medium shadow-md hover:shadow-lg transition-all"
        >
          <Plus className="w-5 h-5" />
          <span>New Conversation</span>
        </button>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={handleCancelDelete}
        >
          <div 
            className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Warning Icon */}
            <div className="flex items-center justify-center mb-4">
              <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                <AlertCircle className="w-8 h-8 text-red-600 dark:text-red-400" />
              </div>
            </div>

            {/* Title */}
            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 text-center mb-2">
              Delete Conversation?
            </h3>

            {/* Description */}
            <p className="text-gray-600 dark:text-gray-400 text-center mb-6">
              Are you sure you want to delete this conversation? This action cannot be undone.
            </p>

            {/* Buttons */}
            <div className="flex gap-3">
              <button
                onClick={handleCancelDelete}
                className="flex-1 px-4 py-2.5 rounded-xl border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="flex-1 px-4 py-2.5 rounded-xl bg-red-500 hover:bg-red-600 text-white transition-colors font-medium flex items-center justify-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ConversationList
