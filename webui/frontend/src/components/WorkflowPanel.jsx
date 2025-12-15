import React, { useState, useEffect } from 'react'
import { FileText, CheckCircle2, Circle, Loader2, Presentation, Image as ImageIcon } from 'lucide-react'

const WorkflowPanel = ({ currentWorkflow, isLoading }) => {
  const [workflow, setWorkflow] = useState(null)

  useEffect(() => {
    if (currentWorkflow) {
      setWorkflow(currentWorkflow)
    }
  }, [currentWorkflow])

  // Default workflow stages
  const defaultStages = [
    { id: 'RAG', name: 'RAG', status: 'pending', description: 'Index documents and run RAG queries ...' },
    { id: 'Summary', name: 'Summary', status: 'pending', description: 'Summarize key content from RAG results ...' },
    { id: 'Plan', name: 'Plan', status: 'pending', description: 'Plan the generation ...' },
    { id: 'Generate', name: 'Generate', status: 'pending', description: 'Generate ...' }
  ]

  const stages = workflow?.stages || defaultStages

  const getStageIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
      case 'active':
        return <Loader2 className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
      default:
        return <Circle className="w-5 h-5 text-gray-300 dark:text-gray-600" />
    }
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900 rounded-2xl shadow-xl overflow-hidden">
      {/* Header - Fixed height for alignment */}
      <div className="flex items-center justify-between px-6 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 h-[72px] flex-shrink-0">
        <div className="flex items-center gap-2">
          {isLoading ? (
            <Loader2 className="w-5 h-5 text-purple-600 dark:text-purple-400 animate-spin" />
          ) : (
            <Presentation className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          )}
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Workflow Status
          </h2>
        </div>
        <span className={`text-xs font-medium px-3 py-1 rounded-full ${
          isLoading 
            ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' 
            : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
        }`}>
          {isLoading ? 'Processing' : 'Ready'}
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {!isLoading && !workflow ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-4">
              <Presentation className="w-8 h-8 text-gray-400 dark:text-gray-600" />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No active workflow
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              Start generating to see progress
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Current Task Info */}
            {workflow && (
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    {workflow.outputType === 'slides' || workflow.outputType === 'ppt' ? (
                      <Presentation className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <ImageIcon className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {workflow.outputType === 'slides' || workflow.outputType === 'ppt' ? 'Generating Slides' : 'Generating Poster'}
                    </div>
                    {workflow.style && (
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        Style: {workflow.style}
                      </div>
                    )}
                    {workflow.content && (
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                        Content: {workflow.content}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Workflow Stages */}
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                Progress
              </h3>
              <div className="space-y-3">
                {stages.map((stage, index) => {
                  const status = stage.status
                  const isActive = status === 'active'
                  const isCompleted = status === 'completed'
                  
                  return (
                    <div key={stage.id} className="relative">
                      {/* Connection Line */}
                      {index < stages.length - 1 && (
                        <div
                          className={`absolute left-5 top-10 w-0.5 h-8 ${
                            isCompleted ? 'bg-green-600 dark:bg-green-400' : 'bg-gray-200 dark:bg-gray-700'
                          }`}
                        />
                      )}
                      
                      {/* Stage Card */}
                      <div
                        className={`relative flex items-start gap-3 p-3 rounded-lg border transition-all ${
                          isActive
                            ? 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20'
                            : isCompleted
                            ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20'
                            : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900'
                        }`}
                      >
                        <div className="flex-shrink-0 mt-0.5">
                          {getStageIcon(status)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div
                            className={`text-sm font-medium ${
                              isActive
                                ? 'text-blue-900 dark:text-blue-100'
                                : isCompleted
                                ? 'text-green-900 dark:text-green-100'
                                : 'text-gray-500 dark:text-gray-400'
                            }`}
                          >
                            {stage.name}
                          </div>
                          {stage.description && (
                            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                              {stage.description}
                            </div>
                          )}
                          {stage.details && (
                            <div className="text-xs text-gray-600 dark:text-gray-500 mt-2 p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
                              {stage.details}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Additional Info */}
            {workflow && workflow.currentStep && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-800">
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  <div className="font-medium mb-1">Current Step:</div>
                  <div>{workflow.currentStep}</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default WorkflowPanel

