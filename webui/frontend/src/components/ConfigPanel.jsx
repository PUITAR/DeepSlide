import React, { useState, useEffect } from 'react'
import { Check, X, FileText, Image, Send, Zap } from 'lucide-react'

const ConfigPanel = ({ 
  content, 
  setContent, 
  style, 
  setStyle, 
  output, 
  setOutput, 
  length, 
  setLength, 
  density, 
  setDensity,
  fastMode = false,
  setFastMode,
  compact = false,
  onRegenerate,
  isLoading = false
}) => {
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [selectedStyleType, setSelectedStyleType] = useState('doraemon') // 'academic', 'doraemon', or 'custom'
  const [customStyle, setCustomStyle] = useState('')

  // Initialize selectedStyleType based on current style
  useEffect(() => {
    if (style === 'academic' || style === 'doraemon') {
      setSelectedStyleType(style)
    } else if (style) {
      // It's a custom style
      setSelectedStyleType('custom')
      setCustomStyle(style)
    }
  }, []) // Only run on mount

  const handleOutputSelect = (selectedOutput) => {
    setOutput(selectedOutput)
    if (!compact) {
      setShowConfigModal(true)
    }
  }

  const handleStyleSelect = (selectedStyle) => {
    setSelectedStyleType(selectedStyle)
    
    if (selectedStyle === 'custom') {
      // If there's already a custom style text, use it
      if (customStyle.trim()) {
        setStyle(customStyle.trim())
      }
      // Otherwise keep current style and wait for user input
    } else {
      // Selected academic or doraemon
      setStyle(selectedStyle)
    }
  }

  const handleCustomStyleChange = (e) => {
    const value = e.target.value
    setCustomStyle(value)
    if (value.trim()) {
      setStyle(value.trim())
    }
  }

  // Segmented control component
  const SegmentedControl = ({ label, options, value, onChange }) => {
    return (
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
        </label>
        <div className="inline-flex items-center bg-gray-50 dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 rounded-xl p-1">
          {options.map((option) => (
            <button
              key={option.value}
              onClick={() => onChange(option.value)}
              className={`flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                value === option.value
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-md'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              {value === option.value && (
                <Check className="w-4 h-4 inline-block mr-1" />
              )}
              {option.label}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="w-full">
      {!compact ? (
        /* Large Card Selection - Initial State */
        <div className="flex gap-4 justify-center">
          {/* Slides Card */}
          <button
            onClick={() => handleOutputSelect('slides')}
            className={`relative flex-1 max-w-xs p-6 rounded-2xl border-2 transition-all ${
              output === 'slides'
                ? 'border-purple-400 bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 shadow-lg'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-purple-300 dark:hover:border-purple-600'
            }`}
          >
            <div className="flex flex-col items-center gap-3">
              <div className={`w-16 h-16 rounded-2xl flex items-center justify-center ${
                output === 'slides'
                  ? 'bg-gradient-to-br from-purple-500 to-pink-500 shadow-md'
                  : 'bg-gray-100 dark:bg-gray-700'
              }`}>
                <FileText className={`w-8 h-8 ${
                  output === 'slides' ? 'text-white' : 'text-gray-400'
                }`} />
              </div>
              <div className="text-center">
                <h3 className={`text-lg font-semibold ${
                  output === 'slides'
                    ? 'text-purple-900 dark:text-purple-100'
                    : 'text-gray-900 dark:text-gray-100'
                }`}>
                  Slides
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Create presentation slides
                </p>
              </div>
              {output === 'slides' && (
                <div className="absolute top-3 right-3">
                  <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                    <Check className="w-4 h-4 text-white" />
                  </div>
                </div>
              )}
            </div>
          </button>

          {/* Poster Card */}
          <button
            onClick={() => handleOutputSelect('poster')}
            className={`relative flex-1 max-w-xs p-6 rounded-2xl border-2 transition-all ${
              output === 'poster'
                ? 'border-purple-400 bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 shadow-lg'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-purple-300 dark:hover:border-purple-600'
            }`}
          >
            <div className="flex flex-col items-center gap-3">
              <div className={`w-16 h-16 rounded-2xl flex items-center justify-center ${
                output === 'poster'
                  ? 'bg-gradient-to-br from-purple-500 to-pink-500 shadow-md'
                  : 'bg-gray-100 dark:bg-gray-700'
              }`}>
                <Image className={`w-8 h-8 ${
                  output === 'poster' ? 'text-white' : 'text-gray-400'
                }`} />
              </div>
              <div className="text-center">
                <h3 className={`text-lg font-semibold ${
                  output === 'poster'
                    ? 'text-purple-900 dark:text-purple-100'
                    : 'text-gray-900 dark:text-gray-100'
                }`}>
                  Poster
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Create infographic poster
                </p>
              </div>
              {output === 'poster' && (
                <div className="absolute top-3 right-3">
                  <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                    <Check className="w-4 h-4 text-white" />
                  </div>
                </div>
              )}
            </div>
          </button>
        </div>
      ) : (
        /* Compact Configuration - Small Card Layout */
        <div className="space-y-4">
          {/* Small Cards Row */}
          <div className="flex items-center gap-3">
            {/* Slides Card - Compact */}
            <button
              onClick={() => {
                setOutput('slides')
                setShowConfigModal(true)
              }}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 transition-all ${
                output === 'slides'
                  ? 'border-purple-400 bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 shadow-md'
                  : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-purple-300 dark:hover:border-purple-600'
              }`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                output === 'slides'
                  ? 'bg-gradient-to-br from-purple-500 to-pink-500'
                  : 'bg-gray-100 dark:bg-gray-700'
              }`}>
                <FileText className={`w-4 h-4 ${
                  output === 'slides' ? 'text-white' : 'text-gray-400'
                }`} />
              </div>
              <div className="flex flex-col items-start">
                <span className={`text-sm font-semibold ${
                  output === 'slides'
                    ? 'text-purple-900 dark:text-purple-100'
                    : 'text-gray-900 dark:text-gray-100'
                }`}>
                  Slides
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Presentation
                </span>
              </div>
              {output === 'slides' && (
                <div className="ml-1">
                  <Check className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                </div>
              )}
            </button>

            {/* Poster Card - Compact */}
            <button
              onClick={() => {
                setOutput('poster')
                setShowConfigModal(true)
              }}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 transition-all ${
                output === 'poster'
                  ? 'border-purple-400 bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 shadow-md'
                  : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-purple-300 dark:hover:border-purple-600'
              }`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                output === 'poster'
                  ? 'bg-gradient-to-br from-purple-500 to-pink-500'
                  : 'bg-gray-100 dark:bg-gray-700'
              }`}>
                <Image className={`w-4 h-4 ${
                  output === 'poster' ? 'text-white' : 'text-gray-400'
                }`} />
              </div>
              <div className="flex flex-col items-start">
                <span className={`text-sm font-semibold ${
                  output === 'poster'
                    ? 'text-purple-900 dark:text-purple-100'
                    : 'text-gray-900 dark:text-gray-100'
                }`}>
                  Poster
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Infographic
                </span>
              </div>
              {output === 'poster' && (
                <div className="ml-1">
                  <Check className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                </div>
              )}
            </button>

            {/* Regenerate Button */}
            <button
              onClick={onRegenerate}
              disabled={isLoading}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all shadow-md hover:shadow-lg disabled:cursor-not-allowed whitespace-nowrap ml-auto ${
                isLoading
                  ? 'bg-gray-200 dark:bg-gray-800 text-gray-400'
                  : 'bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white'
              }`}
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                  <span>Generating...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Regenerate</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Configuration Modal - For both compact and non-compact mode */}
      {showConfigModal && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowConfigModal(false)}
        >
          <div 
            className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-2xl w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Configure {output === 'slides' ? 'Slides' : 'Poster'}
              </h2>
              <button
                onClick={() => setShowConfigModal(false)}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="space-y-6">
              {/* Content Type */}
              <SegmentedControl
                label="Content Type"
                options={[
                  { label: 'Paper', value: 'paper' },
                  { label: 'General', value: 'general' }
                ]}
                value={content}
                onChange={setContent}
              />

              {/* Fast Mode Toggle - Only show for paper content */}
              {content === 'paper' && setFastMode && (
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Processing Mode
                  </label>
                  <div className="inline-flex items-center bg-gray-50 dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 rounded-xl p-1">
                    <button
                      onClick={() => setFastMode(false)}
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                        !fastMode
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-md'
                          : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                      }`}
                    >
                      {!fastMode && <Check className="w-4 h-4" />}
                      Normal
                    </button>
                    <button
                      onClick={() => setFastMode(true)}
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                        fastMode
                          ? 'bg-gradient-to-r from-amber-400 to-orange-400 text-white shadow-md'
                          : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                      }`}
                    >
                      <Zap className={`w-4 h-4 ${fastMode ? 'text-white' : 'text-amber-500'}`} />
                      Fast
                    </button>
                  </div>
                </div>
              )}

              {/* Style */}
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Style
                </label>
                <div className="inline-flex items-center bg-gray-50 dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 rounded-xl p-1">
                  {['academic', 'doraemon', 'custom'].map((styleOption) => {
                    const isSelected = selectedStyleType === styleOption
                    
                    return (
                      <button
                        key={styleOption}
                        onClick={() => handleStyleSelect(styleOption)}
                        className={`flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                          isSelected
                            ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-md'
                            : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                        }`}
                      >
                        {isSelected && (
                          <Check className="w-4 h-4 inline-block mr-1" />
                        )}
                        {styleOption === 'academic' ? 'Academic' : styleOption === 'doraemon' ? 'Doraemon' : 'Custom'}
                      </button>
                    )
                  })}
                </div>
                
                {/* Custom Style Input */}
                {selectedStyleType === 'custom' && (
                  <div className="mt-2">
                    <textarea
                      value={customStyle}
                      onChange={handleCustomStyleChange}
                      placeholder="Describe your custom style..."
                      className="w-full px-3 py-2 text-sm border-2 border-purple-200 dark:border-purple-700 rounded-xl bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-400 focus:border-purple-400 resize-none"
                      rows={2}
                    />
                  </div>
                )}
              </div>

              {/* Conditional Options */}
              {output === 'slides' ? (
                <SegmentedControl
                  label="Length"
                  options={[
                    { label: 'Short (5-8)', value: 'short' },
                    { label: 'Medium (8-12)', value: 'medium' },
                    { label: 'Long (12-15)', value: 'long' }
                  ]}
                  value={length}
                  onChange={setLength}
                />
              ) : (
                <SegmentedControl
                  label="Density"
                  options={[
                    { label: 'Sparse', value: 'sparse' },
                    { label: 'Medium', value: 'medium' },
                    { label: 'Dense', value: 'dense' }
                  ]}
                  value={density}
                  onChange={setDensity}
                />
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowConfigModal(false)}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-medium transition-all shadow-md hover:shadow-lg"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ConfigPanel
