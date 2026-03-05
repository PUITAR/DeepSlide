import React from 'react';
import { Link } from 'react-router-dom';
import { Layout as LayoutIcon } from 'lucide-react';

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="min-h-screen flex flex-col bg-gray-50 h-screen overflow-hidden">
      <header className="bg-white border-b h-14 flex items-center px-4 shadow-sm z-10 flex-shrink-0">
        <Link to="/" className="text-xl font-bold text-blue-600 flex items-center gap-2">
          <LayoutIcon className="w-6 h-6" />
          DeepSlide
        </Link>
      </header>
      <main className="flex-1 flex overflow-hidden">
        {children}
      </main>
    </div>
  );
};

export default Layout;
