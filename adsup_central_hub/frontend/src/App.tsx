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
      <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
      <div className="app-container">
        <Sidebar />
        <main className="main-content" id="main-content" tabIndex={-1}>
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
