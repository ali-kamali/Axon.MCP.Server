import { NavLink, Route, Routes } from "react-router-dom";

import DashboardPage from "./pages/dashboard/DashboardPage";
import FileBrowserPage from "./pages/file_browser/FileBrowserPage";
import JobsPage from "./pages/jobs/JobsPage";
import RepositoryDetailPage from "./pages/repository_detail/RepositoryDetailPage";
import RepositoriesPage from "./pages/repositories/RepositoriesPage";
import SearchPage from "./pages/search/SearchPage";
import SettingsPage from "./pages/settings/SettingsPage";
import MCPTestPage from "./pages/mcp_test/MCPTestPage";
import LoginPage from "./pages/login/LoginPage";
import styles from "./App.module.css";

export default function App() {
  return (
    <div className={styles.app_container}>
      <nav className={styles.nav_container}>
        <div className={styles.nav_brand}>Axon MCP Server</div>
        <ul className={styles.nav_list}>
          <li>
            <NavLink
              to="/"
              className={({ isActive }) =>
                isActive ? `${styles.nav_link} ${styles.nav_link_active}` : styles.nav_link
              }
            >
              Dashboard
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/repositories"
              className={({ isActive }) =>
                isActive ? `${styles.nav_link} ${styles.nav_link_active}` : styles.nav_link
              }
            >
              Repositories
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/search"
              className={({ isActive }) =>
                isActive ? `${styles.nav_link} ${styles.nav_link_active}` : styles.nav_link
              }
            >
              Search
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/mcp-test"
              className={({ isActive }) =>
                isActive ? `${styles.nav_link} ${styles.nav_link_active}` : styles.nav_link
              }
            >
              MCP Test
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/jobs"
              className={({ isActive }) =>
                isActive ? `${styles.nav_link} ${styles.nav_link_active}` : styles.nav_link
              }
            >
              Jobs
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                isActive ? `${styles.nav_link} ${styles.nav_link_active}` : styles.nav_link
              }
            >
              Settings
            </NavLink>
          </li>
        </ul>
      </nav>
      <main className={styles.main_content}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<DashboardPage />} />
          <Route path="/repositories" element={<RepositoriesPage />} />
          <Route path="/repositories/:repositoryId" element={<RepositoryDetailPage />} />
          <Route path="/repositories/:repositoryId/files" element={<FileBrowserPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/mcp-test" element={<MCPTestPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}


