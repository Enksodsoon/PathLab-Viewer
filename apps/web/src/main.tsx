import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App'
import './styles.css'
import '@fontsource-variable/cormorant-garamond/wght.css'
import '@fontsource-variable/source-sans-3/wght.css'
import { ThemeProvider } from './theme/ThemeProvider'
import './theme/theme.css'
import './auth.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode><ThemeProvider><BrowserRouter><App /></BrowserRouter></ThemeProvider></StrictMode>,
)
