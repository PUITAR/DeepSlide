import React from 'react'
import ChatWindow from './components/ChatWindow'

function App() {
  try {
    return (
      <div className="h-screen w-screen bg-[#faf9f6] dark:bg-[#171717]">
        <ChatWindow />
      </div>
    )
  } catch (error) {
    console.error('App render error:', error)
    return (
      <div style={{ padding: '20px', color: 'red' }}>
        <h1>Error Loading App</h1>
        <pre>{error.toString()}</pre>
        <pre>{error.stack}</pre>
      </div>
    )
  }
}

export default App

