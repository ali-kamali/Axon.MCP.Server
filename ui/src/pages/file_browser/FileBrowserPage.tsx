import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getFileContent,
  getRepository,
  listRepositoryFiles,
  type FileContentResponse,
  type FileNode,
  type RepositoryResponse,
} from "../../services/api";
import { FileNodeTypeEnum } from "../../types/enums";
import styles from "./FileBrowserPage.module.css";

type RouteParams = {
  repositoryId: string;
};

type TreeNode = FileNode & {
  children?: TreeNode[];
  isExpanded?: boolean;
  isLoading?: boolean;
};

function enhanceNodes(nodes: FileNode[]): TreeNode[] {
  return nodes.map((node) => ({
    ...node,
    children: node.children ? enhanceNodes(node.children) : undefined,
    isExpanded: node.type === FileNodeTypeEnum.directory ? false : undefined,
    isLoading: false,
  }));
}

function updateTree(nodes: TreeNode[], nodeId: number, updater: (node: TreeNode) => TreeNode): TreeNode[] {
  return nodes.map((node) => {
    if (node.id === nodeId) {
      return updater(node);
    }

    if (node.children && node.children.length > 0) {
      const updatedChildren = updateTree(node.children, nodeId, updater);
      if (updatedChildren !== node.children) {
        return {
          ...node,
          children: updatedChildren,
        } satisfies TreeNode;
      }
    }

    return node;
  });
}

function findNode(nodes: TreeNode[], nodeId: number): TreeNode | null {
  for (const node of nodes) {
    if (node.id === nodeId) {
      return node;
    }
    if (node.children) {
      const match = findNode(node.children, nodeId);
      if (match) {
        return match;
      }
    }
  }
  return null;
}

function formatBytes(value: number): string {
  if (value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const converted = value / 1024 ** exponent;
  return `${converted.toFixed(converted < 10 ? 1 : 0)} ${units[exponent]}`;
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

type TreeProps = {
  nodes: TreeNode[];
  onToggle: (node: TreeNode) => void;
  onSelectFile: (node: TreeNode) => void;
  activeFileId: number | null;
};

function TreeView({ nodes, onToggle, onSelectFile, activeFileId }: TreeProps) {
  return (
    <ul className={styles.tree_list}>
      {nodes.map((node) => {
        const isDirectory = node.type === FileNodeTypeEnum.directory;
        const isActive = node.id === activeFileId;
        return (
          <li key={node.id} className={styles.tree_item}>
            <button
              type="button"
              className={`${styles.tree_button} ${isDirectory ? styles.tree_directory : styles.tree_file} ${
                isActive ? styles.tree_active : ""
              }`}
              onClick={() => (isDirectory ? onToggle(node) : onSelectFile(node))}
            >
              <span className={styles.tree_icon}>
                {isDirectory ? (node.isExpanded ? "▾" : "▸") : "•"}
              </span>
              <span className={styles.tree_name}>{node.name}</span>
              {node.isLoading && <span className={styles.tree_loading}>Loading…</span>}
            </button>
            {isDirectory && node.isExpanded && node.children && node.children.length > 0 && (
              <TreeView
                nodes={node.children}
                onToggle={onToggle}
                onSelectFile={onSelectFile}
                activeFileId={activeFileId}
              />
            )}
            {isDirectory && node.isExpanded && (!node.children || node.children.length === 0) && !node.isLoading && (
              <div className={styles.tree_empty}>Empty directory</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function FileBrowserPage() {
  const { repositoryId } = useParams<RouteParams>();
  const repositoryIdNumber = Number(repositoryId);

  const [repository, setRepository] = useState<RepositoryResponse | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [fileContent, setFileContent] = useState<FileContentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [contentError, setContentError] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);

  const loadInitialData = useCallback(async () => {
    if (Number.isNaN(repositoryIdNumber)) {
      setError("Repository identifier is invalid.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const [repositoryData, rootNodes] = await Promise.all([
        getRepository(repositoryIdNumber),
        listRepositoryFiles(repositoryIdNumber, { depth: 2 }),
      ]);

      setRepository(repositoryData);
      setTree(enhanceNodes(rootNodes));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load file tree";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [repositoryIdNumber]);

  useEffect(() => {
    void loadInitialData();
  }, [loadInitialData]);

  const handleToggle = async (target: TreeNode) => {
    if (target.type !== FileNodeTypeEnum.directory) {
      return;
    }

    const currentNode = findNode(tree, target.id);
    if (!currentNode) {
      return;
    }

    if (currentNode.children && currentNode.children.length > 0) {
      setTree((prev) =>
        updateTree(prev, target.id, (node) => ({
          ...node,
          isExpanded: !node.isExpanded,
        }))
      );
      return;
    }

    setTree((prev) =>
      updateTree(prev, target.id, (node) => ({
        ...node,
        isExpanded: true,
        isLoading: true,
      }))
    );

    try {
      const children = await listRepositoryFiles(repositoryIdNumber, { path: target.path });
      setTree((prev) =>
        updateTree(prev, target.id, (node) => ({
          ...node,
          isExpanded: true,
          isLoading: false,
          children: enhanceNodes(children),
        }))
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load directory contents";
      setError(message);
      setTree((prev) =>
        updateTree(prev, target.id, (node) => ({
          ...node,
          isLoading: false,
        }))
      );
    }
  };

  const handleSelectFile = async (target: TreeNode) => {
    setSelectedFileId(target.id);
    setContentError(null);
    setContentLoading(true);
    try {
      const content = await getFileContent(target.id);
      setFileContent(content);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load file content";
      setContentError(message);
      setFileContent(null);
    } finally {
      setContentLoading(false);
    }
  };

  const selectedNode = useMemo(() => {
    if (!selectedFileId) {
      return null;
    }
    return findNode(tree, selectedFileId);
  }, [tree, selectedFileId]);

  if (Number.isNaN(repositoryIdNumber)) {
    return (
      <div className={styles.browser_container}>
        <div className={styles.error_banner}>Repository identifier must be numeric.</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.browser_container}>
        <div className={styles.loading_panel}>Loading file explorer...</div>
      </div>
    );
  }

  if (error || !repository) {
    return (
      <div className={styles.browser_container}>
        <div className={styles.error_banner}>
          <strong>Error:</strong> {error ?? "Repository not found"}
          <Link className={styles.secondary_button} to="/repositories">
            Back to repositories
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.browser_container}>
      <header className={styles.browser_header}>
        <div className={styles.breadcrumbs}>
          <Link to="/repositories" className={styles.breadcrumb_link}>
            Repositories
          </Link>
          <span className={styles.breadcrumb_separator}>/</span>
          <Link to={`/repositories/${repository.id}`} className={styles.breadcrumb_link}>
            {repository.name}
          </Link>
          <span className={styles.breadcrumb_separator}>/</span>
          <span>Files</span>
        </div>
        <div className={styles.browser_actions}>
          <button className={styles.refresh_button} type="button" onClick={() => void loadInitialData()}>
            Refresh
          </button>
          <Link className={styles.secondary_button} to={`/repositories/${repository.id}`}>
            Repository overview
          </Link>
        </div>
      </header>

      <div className={styles.browser_layout}>
        <aside className={styles.tree_panel}>
          <div className={styles.panel_header}>
            <h2 className={styles.panel_title}>Files</h2>
            <span className={styles.panel_caption}>{tree.length} root entries</span>
          </div>
          {tree.length === 0 ? (
            <p className={styles.panel_hint}>No files have been indexed for this repository.</p>
          ) : (
            <TreeView nodes={tree} onToggle={handleToggle} onSelectFile={handleSelectFile} activeFileId={selectedFileId} />
          )}
        </aside>

        <section className={styles.viewer_panel}>
          {selectedNode && (
            <header className={styles.viewer_header}>
              <div>
                <h2 className={styles.viewer_title}>{selectedNode.path}</h2>
                <div className={styles.viewer_meta}>
                  <span>{selectedNode.language ?? "unknown"}</span>
                  <span>{formatBytes(selectedNode.size_bytes)}</span>
                  <span>Updated {formatTimestamp(selectedNode.last_modified)}</span>
                </div>
              </div>
            </header>
          )}

          {!selectedNode && <p className={styles.viewer_placeholder}>Select a file to view its contents.</p>}

          {contentLoading && <p className={styles.viewer_placeholder}>Loading file content…</p>}

          {contentError && <p className={styles.viewer_error}>{contentError}</p>}

          {fileContent && !contentLoading && !contentError && (
            <article className={styles.code_container}>
              <pre className={styles.code_block}>{fileContent.content}</pre>
            </article>
          )}
        </section>
      </div>
    </div>
  );
}


