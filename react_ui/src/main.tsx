import React from 'react'
import ReactDOM from 'react-dom/client'
import { StarhePlugin } from './StarhePlugin'
import './StarhePlugin/StarhePlugin.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <StarhePlugin />
  </React.StrictMode>,
)
