import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ToolArticle from './pages/ToolArticle';
import ToolAffiliate from './pages/ToolAffiliate';
import ToolFacebook from './pages/ToolFacebook';
import ToolTikTok from './pages/ToolTikTok';
import LoginPage from './pages/LoginPage';
import UserRolesPage from './pages/UserRolesPage';

function AppContent() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>

      {/* News Portal Header */}
      <Header />

      <div className="app-container">
        {/* Editorial Dropdown Sidebar */}
        <Sidebar />

        {/* Main Content Area */}
        <main className="main-content" id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Navigate to="/article" replace />} />
            <Route path="/article" element={<ToolArticle />} />
            <Route path="/affiliate" element={<ToolAffiliate />} />
            <Route path="/facebook" element={<ToolFacebook />} />
            <Route path="/tiktok" element={<ToolTikTok />} />
            <Route path="/admin/users" element={<UserRolesPage />} />
            <Route path="/login" element={<Navigate to="/article" replace />} />
            <Route path="*" element={<Navigate to="/article" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <AppContent />
      </Router>
    </AuthProvider>
  );
}
