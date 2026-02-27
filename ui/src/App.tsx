import { lazy, Suspense } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import styles from "./App.module.css";

const DashboardPage = lazy(() => import("./pages/dashboard/DashboardPage"));
const FileBrowserPage = lazy(() => import("./pages/file_browser/FileBrowserPage"));
const JobsPage = lazy(() => import("./pages/jobs/JobsPage"));
const RepositoryDetailPage = lazy(() => import("./pages/repository_detail/RepositoryDetailPage"));
const RepositoriesPage = lazy(() => import("./pages/repositories/RepositoriesPage"));
const SearchPage = lazy(() => import("./pages/search/SearchPage"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));
const MCPTestPage = lazy(() => import("./pages/mcp_test/MCPTestPage"));
const LoginPage = lazy(() => import("./pages/login/LoginPage"));

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
        <Suspense fallback={<div role="status">Loading page…</div>}>
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
        </Suspense>
      </main>
    </div>
  );
}


