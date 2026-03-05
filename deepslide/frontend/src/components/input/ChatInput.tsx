import React, { useState } from 'react';
import { useProjectStore } from '../../store/useProjectStore';
import { Send, Sparkles } from 'lucide-react';

const ChatInput: React.FC = () => {
  const { executeCommand, isThinking } = useProjectStore();
  const [input, setInput] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    
    const cmd = input;
    setInput('');
    await executeCommand(cmd);
  };

  return (
    <div className="bg-white border-t p-4">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Sparkles className="h-5 w-5 text-purple-500" />
          </div>
          <input
            type="text"
            className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500 focus:border-purple-500 sm:text-sm"
            placeholder="Describe how to modify this slide..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isThinking}
          />
        </div>
        <button
          type="submit"
          disabled={isThinking || !input.trim()}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-lg shadow-sm text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
        >
          {isThinking ? 'Thinking...' : <Send className="w-4 h-4" />}
        </button>
      </form>
    </div>
  );
};

export default ChatInput;
