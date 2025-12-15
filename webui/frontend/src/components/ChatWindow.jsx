import React, { useState, useRef, useEffect, useCallback } from 'react'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import ConversationList from './ConversationList'
import ConfigPanel from './ConfigPanel'
import { PanelLeftOpen, FileText, Download, Eye, X } from 'lucide-react'

// Generate unique ID
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

const ChatWindow = () => {
  // Conversations state
  const [conversations, setConversations] = useState([])
  const [currentConversationId, setCurrentConversationId] = useState(null)
  
  // Current conversation derived state
  const currentConversation = conversations.find(c => c.id === currentConversationId) || null
  const messages = currentConversation?.messages || []
  const conversationFiles = currentConversation?.files || []
  
  const [isLoading, setIsLoading] = useState(false)
  
  // Configuration state - matching main.py parameters
  const [content, setContent] = useState('paper') // 'paper' or 'general'
  const [style, setStyle] = useState('doraemon') // 'academic', 'doraemon', or custom
  const [output, setOutput] = useState('slides') // 'slides' or 'poster'
  const [length, setLength] = useState('medium') // 'short', 'medium', 'long' (for slides)
  const [density, setDensity] = useState('medium') // 'sparse', 'medium', 'dense' (for poster)
  const [fastMode, setFastMode] = useState(true) // Fast mode: parse only, no RAG indexing (only for paper content, default enabled)
  
  const [showLeftPanel, setShowLeftPanel] = useState(true)
  const [currentWorkflow, setCurrentWorkflow] = useState(null) // Now includes conversationId
  const [previewFile, setPreviewFile] = useState(null)
  const messagesEndRef = useRef(null)
  const abortControllerRef = useRef(null)
  
  // Session-level polling intervals: Map<sessionId, intervalId>
  const pollIntervalsRef = useRef(new Map())
  // Track sessions that are currently fetching results to prevent duplicates
  const fetchingResultsRef = useRef(new Set())

  // Load conversations from localStorage on mount
  useEffect(() => {
    const savedConversations = localStorage.getItem('paper2slides_conversations')
    if (savedConversations) {
      try {
        const parsed = JSON.parse(savedConversations)
        setConversations(parsed)
        // Auto-select the most recent conversation
        if (parsed.length > 0) {
          setCurrentConversationId(parsed[0].id)
        }
      } catch (e) {
        console.error('Error loading conversations:', e)
      }
    }
  }, [])

  // Save conversations to localStorage whenever they change
  // Note: blob URLs are temporary and won't work after page reload
  useEffect(() => {
    if (conversations.length > 0) {
      // Clean up conversations before saving - remove blob URLs
      const cleanConversations = conversations.map(conv => ({
        ...conv,
        files: conv.files?.map(f => {
          const { blobUrl, ...cleanFile } = f
          return cleanFile
        }),
        messages: conv.messages?.map(msg => ({
          ...msg,
          files: msg.files?.map(f => {
            const { blobUrl, ...cleanFile } = f
            return cleanFile
          })
        }))
      }))
      localStorage.setItem('paper2slides_conversations', JSON.stringify(cleanConversations))
    }
  }, [conversations])

  // Cleanup polling intervals when component unmounts
  useEffect(() => {
    return () => {
      // Clear all polling intervals
      pollIntervalsRef.current.forEach((intervalId) => {
        clearInterval(intervalId)
      })
      pollIntervalsRef.current.clear()
    }
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // File preview functions
  const openPreview = (file) => {
    setPreviewFile(file)
  }

  const closePreview = () => {
    setPreviewFile(null)
  }

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown size'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const getFileIcon = (file) => {
    const ext = file.name?.split('.').pop()?.toLowerCase()
    if (ext === 'pdf') return '📄'
    if (ext === 'md' || ext === 'markdown') return '📝'
    if (['doc', 'docx'].includes(ext)) return '📃'
    return '📎'
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

  // Generate display name for generated output
  const getOutputDisplayName = (output) => {
    // Format: Slides/Poster - FileName - style - content - length/density
    const parts = []
    
    // Output type
    parts.push(output.outputType === 'slides' || output.outputType === 'ppt' ? 'Slides' : 'Poster')
    
    // Source file name (without extension)
    if (output.sourceFiles && output.sourceFiles.length > 0) {
      const firstFileName = output.sourceFiles[0].replace(/\.[^/.]+$/, '')
      parts.push(firstFileName)
    }
    
    // Style
    if (output.style) {
      parts.push(output.style)
    }
    
    // Content
    if (output.content) {
      parts.push(output.content)
    }
    
    // Length or Density
    if (output.outputType === 'slides' && output.length) {
      parts.push(output.length)
    } else if (output.outputType === 'poster' && output.density) {
      parts.push(output.density)
    }
    
    return parts.join(' - ')
  }

  // Update current conversation
  const updateConversation = useCallback((convId, updates) => {
    setConversations(prev => prev.map(conv => {
      if (conv.id === convId) {
        return {
          ...conv,
          ...updates,
          updatedAt: new Date().toISOString()
        }
      }
      return conv
    }))
  }, [])

  // Add message to current conversation
  const addMessage = useCallback((convId, message) => {
    setConversations(prev => prev.map(conv => {
      if (conv.id === convId) {
        // Check for duplicate messages
        const isDuplicate = conv.messages.some(existing => {
          // For assistant messages with URLs, check URL match
          if (message.role === 'assistant' && existing.role === 'assistant') {
            if (message.pptUrl || message.posterUrl) {
              const samePptUrl = message.pptUrl && existing.pptUrl && message.pptUrl === existing.pptUrl
              const samePosterUrl = message.posterUrl && existing.posterUrl && message.posterUrl === existing.posterUrl
              if (samePptUrl || samePosterUrl) {
                return true
              }
            }
          }
          
          // For other messages, check content and recent timestamp
          const sameContent = existing.content === message.content
          const sameRole = existing.role === message.role
          const recentTimestamp = existing.timestamp && message.timestamp && 
                                 Math.abs(new Date(existing.timestamp).getTime() - new Date(message.timestamp).getTime()) < 3000 // within 3 seconds
          return sameContent && sameRole && recentTimestamp
        })
        
        if (isDuplicate) {
          console.log('Duplicate message detected, skipping...')
          return conv
        }
        
        return {
          ...conv,
          messages: [...conv.messages, message],
          updatedAt: new Date().toISOString()
        }
      }
      return conv
    }))
  }, [])

  // Add files to current conversation
  const addFilesToConversation = useCallback((convId, files) => {
    setConversations(prev => prev.map(conv => {
      if (conv.id === convId) {
        const existingNames = new Set(conv.files.map(f => f.name))
        const newFiles = files.filter(f => !existingNames.has(f.name))
        return {
          ...conv,
          files: [...conv.files, ...newFiles],
          updatedAt: new Date().toISOString()
        }
      }
      return conv
    }))
  }, [])

  // Check if there's an empty conversation to reuse
  const findEmptyConversation = useCallback(() => {
    return conversations.find(conv => 
      conv.messages.length === 0 && 
      conv.files.length === 0 &&
      (!conv.generatedOutputs || conv.generatedOutputs.length === 0)
    )
  }, [conversations])

  // Create new conversation or reuse empty one
  const handleNewConversation = useCallback(() => {
    // Check if there's an empty conversation to reuse
    const emptyConv = findEmptyConversation()
    if (emptyConv) {
      setCurrentConversationId(emptyConv.id)
      return
    }

    const newConv = {
      id: generateId(),
      title: 'New Chat',
      messages: [],
      files: [],
      generatedOutputs: [],
      config: { content, style, output, length, density, fastMode },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    }
    
    // Use React's automatic batching by updating in the same synchronous block
    // First set the new conversation ID, then update the conversations list
    // This ensures the UI switches to the new conversation immediately
    const newId = newConv.id
    setCurrentConversationId(newId)
    setConversations(prev => [newConv, ...prev])
  }, [content, style, output, length, density, fastMode, findEmptyConversation])

  // Select conversation
  const handleSelectConversation = useCallback((convId) => {
    // Batch all state updates together
    const conv = conversations.find(c => c.id === convId)
    
    // Update current conversation ID first
    setCurrentConversationId(convId)
    
    // Then restore config from conversation in a batched manner
    if (conv?.config) {
      // React 18 will automatically batch these updates
      if (conv.config.content !== undefined) setContent(conv.config.content)
      if (conv.config.style !== undefined) setStyle(conv.config.style)
      if (conv.config.output !== undefined) setOutput(conv.config.output)
      if (conv.config.length !== undefined) setLength(conv.config.length)
      if (conv.config.density !== undefined) setDensity(conv.config.density)
      if (conv.config.fastMode !== undefined) setFastMode(conv.config.fastMode)
    }
  }, [conversations])

  // Delete conversation
  const handleDeleteConversation = useCallback((convId) => {
    setConversations(prev => {
      const filtered = prev.filter(c => c.id !== convId)
      // If deleting current conversation, select another one
      if (convId === currentConversationId && filtered.length > 0) {
        setCurrentConversationId(filtered[0].id)
      } else if (filtered.length === 0) {
        setCurrentConversationId(null)
      }
      // Clear localStorage if no conversations left
      if (filtered.length === 0) {
        localStorage.removeItem('paper2slides_conversations')
      }
      return filtered
    })
  }, [currentConversationId])

  // Cancel generation function
  const handleCancelGeneration = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      
      // Clear workflow interval
      if (typeof window !== 'undefined' && window.workflowInterval) {
        clearInterval(window.workflowInterval)
        window.workflowInterval = null
      }
      
      // Send cancel request to backend and clear polling for this session
      // Get session_id from conversation files
      if (currentConversation && conversationFiles.length > 0) {
        const sessionId = conversationFiles[0]?.sessionId
        if (sessionId) {
          try {
            await fetch(`/api/cancel/${sessionId}`, { method: 'POST' })
            console.log('Cancellation request sent to backend')
            
            // Clear polling interval for this session
            const intervalId = pollIntervalsRef.current.get(sessionId)
            if (intervalId) {
              clearInterval(intervalId)
              pollIntervalsRef.current.delete(sessionId)
              console.log(`Cleared polling for session ${sessionId}`)
            }
          } catch (error) {
            console.error('Failed to send cancellation request:', error)
          }
        }
      }
      
      // Reset states
      setCurrentWorkflow(null)
      setIsLoading(false)
      
      // Note: The cancel message will be added in the catch block when AbortError is caught
      // Files with blobUrl will remain available for preview
    }
  }, [currentConversation, conversationFiles])

  // Fetch final result when pipeline completes
  const fetchFinalResult = async (sessionId, convId) => {
    // Prevent duplicate calls for the same session
    if (fetchingResultsRef.current.has(sessionId)) {
      console.log(`Already fetching result for session ${sessionId}, skipping...`)
      return
    }
    
    fetchingResultsRef.current.add(sessionId)
    
    try {
      const resultResponse = await fetch(`/api/result/${sessionId}`)
      if (resultResponse.ok) {
        const resultData = await resultResponse.json()
        
        // Add assistant message with results
        const assistantMessage = {
          id: generateId(),
          role: 'assistant',
          content: resultData.message || '',  // Empty string to not show success message
          slides: resultData.slides || [],
          pptUrl: resultData.ppt_url || null,
          posterUrl: resultData.poster_url || null,
          config: { content, style, output, length, density, fastMode },
          timestamp: new Date().toISOString()
        }
        
        addMessage(convId, assistantMessage)
        
        // Add generated output to conversation (check for duplicates first)
        const conv = conversations.find(c => c.id === convId)
        const generatedOutput = {
          id: generateId(),
          outputType: output,
          style: style,
          content: content,
          length: output === 'slides' ? length : undefined,
          density: output === 'poster' ? density : undefined,
          pptUrl: resultData.ppt_url || null,
          posterUrl: resultData.poster_url || null,
          slides: resultData.slides || [],
          sourceFiles: (conv?.files || []).map(f => f.name),
          timestamp: new Date().toISOString()
        }
        
        setConversations(prev => prev.map(conv => {
          if (conv.id === convId) {
            // Check if this output already exists (based on pptUrl/posterUrl)
            const existingOutputs = conv.generatedOutputs || []
            const isDuplicate = existingOutputs.some(existing => {
              // Check if URLs match (for either ppt or poster)
              const samePptUrl = existing.pptUrl && generatedOutput.pptUrl && existing.pptUrl === generatedOutput.pptUrl
              const samePosterUrl = existing.posterUrl && generatedOutput.posterUrl && existing.posterUrl === generatedOutput.posterUrl
              return samePptUrl || samePosterUrl
            })
            
            if (isDuplicate) {
              console.log('Duplicate output detected, skipping...')
              return conv
            }
            
            return {
              ...conv,
              generatedOutputs: [...existingOutputs, generatedOutput],
              updatedAt: new Date().toISOString()
            }
          }
          return conv
        }))
        
        // Remove from fetching set after successful completion
        fetchingResultsRef.current.delete(sessionId)
        
        // Clear workflow and loading immediately
        setCurrentWorkflow(null)
        setIsLoading(false)
      } else if (resultResponse.status === 202) {
        // Still processing, wait a bit and try again
        console.log('Result not ready yet, retrying...')
        // Remove from set temporarily to allow retry
        fetchingResultsRef.current.delete(sessionId)
        setTimeout(() => fetchFinalResult(sessionId, convId), 2000)
      } else {
        fetchingResultsRef.current.delete(sessionId)
        throw new Error(`Failed to fetch result: ${resultResponse.status}`)
      }
    } catch (error) {
      console.error('Error fetching final result:', error)
      fetchingResultsRef.current.delete(sessionId)
      const errorMessage = {
        id: generateId(),
        role: 'assistant',
        content: 'Generation completed but failed to fetch results. Please check the output directory.',
        isError: true,
        timestamp: new Date().toISOString()
      }
      addMessage(convId, errorMessage)
      setCurrentWorkflow(null)
      setIsLoading(false)
    }
  }

  const handleSendMessage = async (text, files) => {
    if (!text.trim() && files.length === 0) return

    // Create new conversation if none exists, or reuse empty one
    let convId = currentConversationId
    if (!convId) {
      const emptyConv = findEmptyConversation()
      if (emptyConv) {
        convId = emptyConv.id
        setCurrentConversationId(convId)
      } else {
        const newConv = {
          id: generateId(),
          title: 'New Chat',
          messages: [],
          files: [],
          generatedOutputs: [],
          config: { content, style, output, length, density, fastMode },
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        }
        convId = newConv.id
        // Set conversation ID first, then add to list
        setCurrentConversationId(convId)
        setConversations(prev => [newConv, ...prev])
      }
    }

    // Create blob URLs for immediate preview
    const filesWithBlobUrls = files.map(f => {
      const isPdf = f.type === 'application/pdf' || f.name?.toLowerCase().endsWith('.pdf')
      const blobUrl = isPdf ? URL.createObjectURL(f) : null
      return { 
        name: f.name, 
        size: f.size, 
        type: f.type || 'application/pdf',
        blobUrl: blobUrl,
        url: null  // Will be set after backend response
      }
    })

    const userMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      files: filesWithBlobUrls,
      config: { content, style, output, length, density, fastMode },
      timestamp: new Date().toISOString()
    }

    // Add user message
    addMessage(convId, userMessage)
    
    // Add files to conversation with blob URLs
    if (files.length > 0) {
      const fileInfos = filesWithBlobUrls.map(file => ({
        name: file.name,
        filename: file.name,
        size: file.size,
        type: file.type,
        blobUrl: file.blobUrl,
        url: null  // Will be set after backend response
      }))
      addFilesToConversation(convId, fileInfos)
      
      // Update conversation title based on first file
      const conv = conversations.find(c => c.id === convId)
      if (conv && (!conv.files || conv.files.length === 0)) {
        const fileName = files[0].name.replace(/\.[^/.]+$/, '')
        updateConversation(convId, { title: fileName })
      }
    }

    // Save current config to conversation
    updateConversation(convId, {
      config: { content, style, output, length, density, fastMode }
    })

    setIsLoading(true)

    // Initialize workflow with correct backend stages
    const workflow = {
      outputType: output,
      style: style,
      content: content,
      conversationId: convId, // Track which conversation this workflow belongs to
      stages: [
        { id: 'rag', name: 'RAG', status: 'pending', description: 'Building knowledge graph from documents' },
        { id: 'summary', name: 'Summary', status: 'pending', description: 'Extracting and summarizing key content' },
        { id: 'plan', name: 'Plan', status: 'pending', description: 'Planning content structure and sections' },
        { id: 'generate', name: 'Generate', status: 'pending', description: 'Generating final slides/poster' }
      ],
      currentStep: 'Initializing...'
    }
    setCurrentWorkflow(workflow)

    try {
      // Create abort controller for cancellation
      abortControllerRef.current = new AbortController()

      const formData = new FormData()
      formData.append('message', text)
      formData.append('content', content)
      formData.append('output_type', output)
      formData.append('style', style)
      if (output === 'slides') {
        formData.append('length', length)
      } else {
        formData.append('density', density)
      }
      // Fast mode only applies to paper content
      if (content === 'paper') {
        formData.append('fast_mode', fastMode ? 'true' : 'false')
      }
      
      files.forEach((file) => {
        formData.append('files', file)
      })

      const response = await fetch('/api/chat', {
        method: 'POST',
        body: formData,
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        if (response.status === 409) {
          // Session conflict - another session is running
          throw new Error(errorData.detail || 'Another session is already running. Please wait for it to complete.')
        }
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      
      // Get session_id from response
      const sessionId = data.session_id
      
      // Start polling for status updates
      if (sessionId) {
        // Clear any existing polling for this session
        if (pollIntervalsRef.current.has(sessionId)) {
          clearInterval(pollIntervalsRef.current.get(sessionId))
        }
        
        const statusPollInterval = setInterval(async () => {
          try {
            const statusResponse = await fetch(`/api/status/${sessionId}`)
            if (statusResponse.ok) {
              const statusData = await statusResponse.json()
              const stages = statusData.stages || {}
              
              console.log('[Status Poll]', sessionId.substring(0, 8), 'stages:', stages)
              
              // Update workflow based on backend stages
              setCurrentWorkflow(prev => {
                // Don't clear workflow if prev is null - keep the last known state
                // This can happen if there's a race condition with state updates
                if (!prev) {
                  console.warn('Workflow state is null during polling, skipping update')
                  return prev
                }
                
                const newStages = prev.stages.map(stage => {
                  const backendStatus = stages[stage.id]
                  let status = 'pending'
                  if (backendStatus === 'completed') status = 'completed'
                  else if (backendStatus === 'running') status = 'active'
                  else if (backendStatus === 'failed') status = 'failed'
                  return { ...stage, status }
                })
                
                // Determine current step
                const activeStage = newStages.find(s => s.status === 'active')
                const currentStep = activeStage ? `${activeStage.name}: ${activeStage.description}` : 'Processing...'
                
                return {
                  ...prev,
                  stages: newStages,
                  currentStep: currentStep,
                  error: statusData.error
                }
              })
              
              // Check if all completed or any failed
              const allCompleted = Object.values(stages).every(s => s === 'completed')
              const anyFailed = Object.values(stages).some(s => s === 'failed')
              
              if (allCompleted || anyFailed) {
                // Clear only this session's polling interval FIRST
                const intervalId = pollIntervalsRef.current.get(sessionId)
                if (intervalId) {
                  clearInterval(intervalId)
                  pollIntervalsRef.current.delete(sessionId)
                  console.log(`Stopped polling for session ${sessionId.substring(0, 8)}`)
                }
                
                // If all completed, fetch the final result (only if not already fetching)
                if (allCompleted && !fetchingResultsRef.current.has(sessionId)) {
                  fetchFinalResult(sessionId, convId)
                } else if (anyFailed) {
                  // If failed, add error message and clear workflow
                  const errorMessage = {
                    id: generateId(),
                    role: 'assistant',
                    content: `Generation failed: ${statusData.error || 'Unknown error occurred'}`,
                    isError: true,
                    timestamp: new Date().toISOString()
                  }
                  addMessage(convId, errorMessage)
                  setCurrentWorkflow(null)
                  setIsLoading(false)
                }
              }
            }
          } catch (err) {
            console.error('Error polling status:', err)
          }
        }, 1500) // Poll every 1.5 seconds
        
        // Store interval for this specific session
        pollIntervalsRef.current.set(sessionId, statusPollInterval)
      }

      // Update conversation files and messages with URLs from backend
      if (data.uploaded_files && data.uploaded_files.length > 0) {
        setConversations(prev => prev.map(conv => {
          if (conv.id === convId) {
            // Update files in conversation
            const updatedFiles = conv.files.map(file => {
              const uploadedFile = data.uploaded_files.find(uf => uf.name === file.name)
              if (uploadedFile) {
                // Clean up blob URL if exists
                if (file.blobUrl) {
                  URL.revokeObjectURL(file.blobUrl)
                }
                return { ...file, url: uploadedFile.url, sessionId: data.session_id, blobUrl: null }
              }
              return file
            })
            
            // Update files in messages too
            const updatedMessages = conv.messages.map(msg => {
              if (msg.files && msg.files.length > 0) {
                const updatedMsgFiles = msg.files.map(file => {
                  const uploadedFile = data.uploaded_files.find(uf => uf.name === file.name)
                  if (uploadedFile) {
                    if (file.blobUrl) {
                      URL.revokeObjectURL(file.blobUrl)
                    }
                    return { ...file, url: uploadedFile.url, blobUrl: null }
                  }
                  return file
                })
                return { ...msg, files: updatedMsgFiles }
              }
              return msg
            })
            
            return { ...conv, files: updatedFiles, messages: updatedMessages }
          }
          return conv
        }))
      }

    } catch (error) {
      console.error('Error sending message:', error)
      
      // Clear status poll interval
      if (typeof window !== 'undefined' && window.statusPollInterval) {
        clearInterval(window.statusPollInterval)
        window.statusPollInterval = null
      }
      
      setCurrentWorkflow(null)
      setIsLoading(false)
      
      // Check if it was a user cancellation
      if (error.name === 'AbortError') {
        const cancelMessage = {
          id: generateId(),
          role: 'assistant',
          content: 'Generation cancelled by user.',
          isError: false,
          timestamp: new Date().toISOString()
        }
        addMessage(convId, cancelMessage)
      } else {
        // Check if it's a session conflict error (409)
        const errorContent = error.message.includes('Another session is already running') 
          ? error.message 
          : 'Sorry, an error occurred. Please try again later.'
        
        const errorMessage = {
          id: generateId(),
          role: 'assistant',
          content: errorContent,
          isError: true,
          timestamp: new Date().toISOString()
        }
        addMessage(convId, errorMessage)
      }
      
      abortControllerRef.current = null
    }
    // Don't set isLoading to false in finally block!
    // Let the polling interval or error handler control it
  }

  const handleRegenerate = async () => {
    if (!currentConversationId || !currentConversation) return
    
    // Check if conversation has files
    if (conversationFiles.length === 0) {
      alert('Please upload files first before generating.')
      return
    }
    
    // Get session_id from the first file (all files in a conversation share the same session)
    const sessionId = conversationFiles[0]?.sessionId
    
    if (!sessionId) {
      alert('Session ID not found. Please upload files again.')
      return
    }

    const userMessage = {
      id: generateId(),
      role: 'user',
      content: 'Regenerate with current settings',
      config: { content, style, output, length, density, fastMode },
      timestamp: new Date().toISOString()
    }

    // Add user message
    addMessage(currentConversationId, userMessage)

    setIsLoading(true)

    // Initialize workflow with correct backend stages
    const workflow = {
      outputType: output,
      style: style,
      content: content,
      conversationId: currentConversationId, // Track which conversation this workflow belongs to
      stages: [
        { id: 'rag', name: 'RAG', status: 'pending', description: 'Building knowledge graph from documents' },
        { id: 'summary', name: 'Summary', status: 'pending', description: 'Extracting and summarizing key content' },
        { id: 'plan', name: 'Plan', status: 'pending', description: 'Planning content structure and sections' },
        { id: 'generate', name: 'Generate', status: 'pending', description: 'Generating final slides/poster' }
      ],
      currentStep: 'Initializing...'
    }
    setCurrentWorkflow(workflow)

    try {
      // Create abort controller for cancellation
      abortControllerRef.current = new AbortController()

      // Reuse existing session - no need to upload files again
      const formData = new FormData()
      formData.append('message', '')  // Empty message to avoid treating as custom style
      formData.append('content', content)
      formData.append('output_type', output)
      formData.append('style', style)
      formData.append('session_id', sessionId)  // Pass session_id to reuse files
      if (output === 'slides') {
        formData.append('length', length)
      } else {
        formData.append('density', density)
      }
      // Fast mode only applies to paper content
      if (content === 'paper') {
        formData.append('fast_mode', fastMode ? 'true' : 'false')
      }

      const response = await fetch('/api/chat', {
        method: 'POST',
        body: formData,
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        if (response.status === 409) {
          // Session conflict - another session is running
          throw new Error(errorData.detail || 'Another session is already running. Please wait for it to complete.')
        }
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      
      // Start polling for status updates using the sessionId
      // Note: Don't clear the interval here! Let it run until all stages complete
      if (sessionId) {
        // Clear any existing polling for this session
        if (pollIntervalsRef.current.has(sessionId)) {
          clearInterval(pollIntervalsRef.current.get(sessionId))
        }
        
        const statusPollInterval = setInterval(async () => {
          try {
            const statusResponse = await fetch(`/api/status/${sessionId}`)
            if (statusResponse.ok) {
              const statusData = await statusResponse.json()
              const stages = statusData.stages || {}
              
              console.log('[Regenerate Status Poll]', sessionId.substring(0, 8), 'stages:', stages)
              
              // Update workflow based on backend stages
              setCurrentWorkflow(prev => {
                // Don't clear workflow if prev is null - keep the last known state
                // This can happen if there's a race condition with state updates
                if (!prev) {
                  console.warn('Workflow state is null during polling, skipping update')
                  return prev
                }
                
                const newStages = prev.stages.map(stage => {
                  const backendStatus = stages[stage.id]
                  let status = 'pending'
                  if (backendStatus === 'completed') status = 'completed'
                  else if (backendStatus === 'running') status = 'active'
                  else if (backendStatus === 'failed') status = 'failed'
                  return { ...stage, status }
                })
                
                // Determine current step
                const activeStage = newStages.find(s => s.status === 'active')
                const currentStep = activeStage ? `${activeStage.name}: ${activeStage.description}` : 'Processing...'
                
                return {
                  ...prev,
                  stages: newStages,
                  currentStep: currentStep,
                  error: statusData.error
                }
              })
              
              // Check if all completed or any failed
              const allCompleted = Object.values(stages).every(s => s === 'completed')
              const anyFailed = Object.values(stages).some(s => s === 'failed')
              
              if (allCompleted || anyFailed) {
                // Clear only this session's polling interval FIRST
                const intervalId = pollIntervalsRef.current.get(sessionId)
                if (intervalId) {
                  clearInterval(intervalId)
                  pollIntervalsRef.current.delete(sessionId)
                  console.log(`Stopped polling for session ${sessionId.substring(0, 8)}`)
                }
                
                // If all completed, fetch the final result (only if not already fetching)
                if (allCompleted && !fetchingResultsRef.current.has(sessionId)) {
                  fetchFinalResult(sessionId, currentConversationId)
                } else if (anyFailed) {
                  // If failed, add error message and clear workflow
                  const errorMessage = {
                    id: generateId(),
                    role: 'assistant',
                    content: `Generation failed: ${statusData.error || 'Unknown error occurred'}`,
                    isError: true,
                    timestamp: new Date().toISOString()
                  }
                  addMessage(currentConversationId, errorMessage)
                  setCurrentWorkflow(null)
                  setIsLoading(false)
                }
              }
            }
          } catch (err) {
            console.error('Error polling status:', err)
          }
        }, 1500) // Poll every 1.5 seconds
        
        // Store interval for this specific session
        pollIntervalsRef.current.set(sessionId, statusPollInterval)
      }

    } catch (error) {
      console.error('Error regenerating:', error)
      
      if (typeof window !== 'undefined' && window.workflowInterval) {
        clearInterval(window.workflowInterval)
        window.workflowInterval = null
      }
      
      setCurrentWorkflow(null)
      setIsLoading(false)
      
      // Check if it was a user cancellation
      if (error.name === 'AbortError') {
        const cancelMessage = {
          id: generateId(),
          role: 'assistant',
          content: 'Generation cancelled by user.',
          isError: false,
          timestamp: new Date().toISOString()
        }
        addMessage(currentConversationId, cancelMessage)
      } else {
        const errorMessage = {
          id: generateId(),
          role: 'assistant',
          content: 'Failed to regenerate. Please try again.',
          isError: true,
          timestamp: new Date().toISOString()
        }
        addMessage(currentConversationId, errorMessage)
      }
      
      abortControllerRef.current = null
    }
    // Don't set isLoading to false in finally block!
    // Let the polling interval or error handler control it
  }

  const handleSelectFile = (file) => {
    // When a file is selected from conversation, it's already in the current conversation
    console.log('File selected:', file)
  }

  return (
    <div className="flex h-full w-full bg-gradient-to-br from-purple-50 via-pink-50 to-purple-100 dark:bg-gradient-to-br dark:from-purple-900/20 dark:via-pink-900/20 dark:to-purple-900/30 p-4 gap-4">
      {/* Left Panel - Conversation List */}
      {showLeftPanel && (
        <div className="w-80 flex-shrink-0">
          <ConversationList
            conversations={conversations}
            currentConversationId={currentConversationId}
            onSelectConversation={handleSelectConversation}
            onNewConversation={handleNewConversation}
            onDeleteConversation={handleDeleteConversation}
            onCollapse={() => setShowLeftPanel(false)}
          />
        </div>
      )}

      {/* Middle Panel - Chat Card */}
      <div className="flex flex-col flex-1 min-w-0 bg-white dark:bg-gray-900 rounded-2xl shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 h-[72px] flex-shrink-0">
          <div className="flex items-center space-x-3">
            {/* Show expand button only when sidebar is collapsed */}
            {!showLeftPanel && (
              <button
                onClick={() => setShowLeftPanel(true)}
                className="p-2 rounded-lg hover:bg-purple-50 dark:hover:bg-gray-800 transition-colors"
                title="Show sidebar"
              >
                <PanelLeftOpen className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
            )}
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg">
              <span className="text-white text-sm font-bold">P2S</span>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Paper2Slides
              </h1>
              {currentConversation && (
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[200px]">
                  {currentConversation.title || 'New Chat'}
                </p>
              )}
            </div>
          </div>

          {/* Current conversation files indicator */}
          {conversationFiles.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
              <FileText className="w-4 h-4 text-purple-600 dark:text-purple-400" />
              <span className="text-sm text-purple-700 dark:text-purple-300">
                {conversationFiles.length} file{conversationFiles.length > 1 ? 's' : ''}
              </span>
            </div>
          )}
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto bg-gradient-to-b from-white to-purple-50/30 dark:from-gray-900 dark:to-purple-900/10">
          <div className="max-w-4xl mx-auto px-4">
            {!currentConversation ? (
              <div className="flex flex-col items-center justify-center h-full min-h-[50vh] text-center">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center mb-6 shadow-xl">
                  <span className="text-white text-3xl font-bold">P2S</span>
                </div>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-3">
                  Welcome to Paper2Slides
                </h2>
                <p className="text-base text-gray-600 dark:text-gray-400 max-w-xl mb-6">
                  Upload your documents <span className="whitespace-nowrap">(PDF, DOC, DOCX, Markdown)</span> and I'll transform them into stunning presentations
                </p>
                <button
                  onClick={handleNewConversation}
                  className="px-6 py-3 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-medium shadow-lg hover:shadow-xl transition-all"
                >
                  Start New Conversation
                </button>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full min-h-[50vh] text-center">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center mb-6 shadow-xl">
                  <span className="text-white text-3xl font-bold">P2S</span>
                </div>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-3">
                  Ready to create your presentation
                </h2>
                <p className="text-base text-gray-600 dark:text-gray-400 max-w-xl">
                  Upload your documents <span className="whitespace-nowrap">(PDF, DOC, DOCX, Markdown)</span> to get started
                </p>
                {conversationFiles.length > 0 && (
                  <div className="mt-6 p-4 bg-purple-50 dark:bg-purple-900/20 rounded-xl">
                    <p className="text-sm text-purple-700 dark:text-purple-300 mb-3">
                      This conversation has {conversationFiles.length} file{conversationFiles.length > 1 ? 's' : ''}:
                    </p>
                    <div className="flex flex-wrap gap-3">
                      {conversationFiles.map((file, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border border-purple-200 dark:border-purple-700 rounded-lg text-xs relative group"
                        >
                          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 via-pink-500 to-rose-500 flex items-center justify-center flex-shrink-0 shadow-sm">
                            <FileText className="w-4 h-4 text-white" />
                          </div>
                          <span className="text-gray-700 dark:text-gray-300 pr-6">{file.name}</span>
                          <button
                            type="button"
                            onClick={() => openPreview(file)}
                            className="absolute right-1 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900/50 hover:bg-purple-200 dark:hover:bg-purple-900 text-purple-600 dark:text-purple-300 transition-all opacity-0 group-hover:opacity-100"
                            title="Preview file"
                          >
                            <Eye className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <MessageList 
                messages={messages}
                uploadedFiles={conversationFiles}
                currentWorkflow={currentWorkflow}
                isLoading={isLoading}
                onCancelGeneration={handleCancelGeneration}
                conversationId={currentConversationId}
              />
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Configuration Panel - Always show when conversation exists */}
        {currentConversation && (
          <div className="border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 px-6 py-3">
            <ConfigPanel
              content={content}
              setContent={setContent}
              style={style}
              setStyle={setStyle}
              output={output}
              setOutput={setOutput}
              length={length}
              setLength={setLength}
              density={density}
              setDensity={setDensity}
              fastMode={fastMode}
              setFastMode={setFastMode}
              compact={messages.length > 0}
              onRegenerate={handleRegenerate}
              isLoading={isLoading}
            />
          </div>
        )}

        {/* Input Area */}
        {currentConversation && (
          <MessageInput
            onSendMessage={handleSendMessage} 
            isLoading={isLoading}
            outputType={output}
            style={style}
            preSelectedFiles={[]}
            onPreSelectedFilesClear={() => {}}
            hasMessages={messages.length > 0}
          />
        )}
      </div>

      {/* Right Panel - Current Conversation Details (optional, can show generated outputs) */}
      {currentConversation && currentConversation.generatedOutputs && currentConversation.generatedOutputs.length > 0 && (
        <div className="w-72 flex-shrink-0 bg-white dark:bg-gray-900 rounded-2xl shadow-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-4 border-b border-gray-100 dark:border-gray-800">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Generated Outputs
            </h2>
          </div>
          <div className="p-3 space-y-2 overflow-y-auto max-h-[calc(100vh-180px)]">
            {currentConversation.generatedOutputs.map((output, idx) => (
              <div key={output.id || idx} className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
                <div className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1">
                  {getOutputDisplayName(output)}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  {new Date(output.timestamp).toLocaleString('en-US', { 
                    month: 'numeric', 
                    day: 'numeric', 
                    year: 'numeric', 
                    hour: 'numeric', 
                    minute: '2-digit', 
                    hour12: true 
                  })}
                </div>
                {(output.pptUrl || output.posterUrl) && (
                  <a
                    href={output.pptUrl || output.posterUrl}
                    download
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white text-xs rounded-lg transition-all"
                  >
                    <Download className="w-3 h-3" />
                    Download
                  </a>
                )}
              </div>
            ))}
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
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 via-pink-500 to-rose-500 flex items-center justify-center shadow-lg">
                <FileText className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
                  {previewFile.name || previewFile.filename}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {formatFileSize(previewFile.size)} • {getFileTypeName(previewFile)}
                </p>
              </div>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-auto p-6">
              {(previewFile.url || previewFile.blobUrl) && (previewFile.type === 'application/pdf' || previewFile.name?.toLowerCase().endsWith('.pdf')) ? (
                <iframe
                  src={previewFile.url || previewFile.blobUrl}
                  className="w-full h-[60vh] rounded-lg border border-gray-200 dark:border-gray-700"
                  title="PDF Preview"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-[40vh] text-center">
                  <div className="w-28 h-28 rounded-3xl bg-gradient-to-br from-purple-500 via-pink-500 to-rose-500 flex items-center justify-center mb-6 shadow-xl">
                    <FileText className="w-14 h-14 text-white" />
                  </div>
                  <h4 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    {previewFile.name || previewFile.filename}
                  </h4>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                    {(previewFile.url || previewFile.blobUrl) ? 'Preview not available for this file type' : 'File preview not available - file needs to be uploaded first'}
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

export default ChatWindow
