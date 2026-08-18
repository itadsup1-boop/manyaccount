import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

// Import các UI components riêng lẻ
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import ToolArticle from './pages/ToolArticle';
import ToolFacebook from './pages/ToolFacebook';
import ToolTikTok from './pages/ToolTikTok';

export default function App() {
  return (
    <Router>
      <div className="app-container">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/article" element={<ToolArticle />} />
            <Route path="/facebook" element={<ToolFacebook />} />
            <Route path="/tiktok" element={<ToolTikTok />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
