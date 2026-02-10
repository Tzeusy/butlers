import { RouterProvider } from 'react-router'
import { router } from './router.tsx'
import './App.css'

function App() {
  return <RouterProvider router={router} />
}

export default App
