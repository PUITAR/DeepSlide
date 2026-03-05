import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { prism } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css';

interface MarkdownRendererProps {
  content: string;
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  const components: Components = {
    code(props) {
      const rest = props as unknown as { inline?: boolean; className?: string; children?: React.ReactNode } & Record<string, unknown>;
      const inline = Boolean(rest.inline);
      const className = typeof rest.className === 'string' ? rest.className : undefined;
      const children = rest.children;
      const match = /language-(\w+)/.exec(className || '');
      return !inline && match ? (
        <SyntaxHighlighter style={prism} language={match[1]} PreTag="div" {...rest}>
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code
          className={className ? className : 'bg-gray-100 rounded px-1 py-0.5 text-sm font-mono text-red-500'}
          {...rest}
        >
          {children}
        </code>
      );
    },
    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
    ul: ({ children }) => <ul className="list-disc pl-4 mb-2">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2">{children}</ol>,
    li: ({ children }) => <li className="mb-1">{children}</li>,
    h1: ({ children }) => <h1 className="text-xl font-bold mb-2 mt-4">{children}</h1>,
    h2: ({ children }) => <h2 className="text-lg font-bold mb-2 mt-3">{children}</h2>,
    h3: ({ children }) => <h3 className="text-md font-bold mb-1 mt-2">{children}</h3>,
    blockquote: ({ children }) => (
      <blockquote className="border-l-4 border-gray-300 pl-4 italic my-2 text-gray-600">{children}</blockquote>
    ),
    a: ({ href, children }) => (
      <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ),
    table: ({ children }) => (
      <div className="overflow-x-auto my-2">
        <table className="min-w-full divide-y divide-gray-200 border">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="px-3 py-2 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b">
        {children}
      </th>
    ),
    td: ({ children }) => <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500 border-b">{children}</td>,
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
};

export default MarkdownRenderer;
