import axios from "axios";

import {
  AccessModifierEnum,
  FileNodeTypeEnum,
  JobStatusEnum,
  LanguageEnum,
  RelationTypeEnum,
  RepositoryStatusEnum,
  SourceControlProviderEnum,
  SymbolKindEnum,
  WorkerStatusEnum,
} from "../types/enums";

// Always use relative URLs when behind nginx proxy
// If VITE_API_BASE_URL is set (for local dev), use it, otherwise empty string for relative URLs
const baseURL = import.meta.env.VITE_API_BASE_URL || "";

export const api = axios.create({
  baseURL,
  timeout: 20000,
});

// Request interceptor (API Key removed)
api.interceptors.request.use((config) => {
  return config;
});

// Handle 401 Unauthorized errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login page if not already there
      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export async function login(password: string): Promise<void> {
  await api.post("/api/v1/auth/login", { password });
}

export async function logout(): Promise<void> {
  await api.post("/api/v1/auth/logout");
  window.location.href = "/login";
}

export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

export type RepositoryResponse = {
  id: number;
  provider: SourceControlProviderEnum;
  // GitLab specific fields
  gitlab_project_id?: number;
  // Azure DevOps specific fields
  azuredevops_project_name?: string;
  azuredevops_repo_id?: string;
  // Common fields
  name: string;
  path_with_namespace: string;
  url: string;
  clone_url: string;
  default_branch: string;
  status: RepositoryStatusEnum;
  last_synced_at: string | null;
  last_commit_sha: string | null;
  total_files: number;
  total_symbols: number;
  size_bytes: number;

  // Enhanced statistics
  languages: Record<string, number>;
  primary_language: string | null;

  // Last commit info
  last_commit: {
    sha: string;
    message: string;
    author_name: string | null;
    committed_date: string | null;
  } | null;

  created_at: string;
  updated_at: string;
};

export type RepositoryUpdatePayload = Partial<RepositoryCreatePayload> & {
  description?: string;
};

export type RepositoryCreatePayload = {
  provider: SourceControlProviderEnum;
  // GitLab specific fields
  gitlab_project_id?: number;
  // Azure DevOps specific fields
  azuredevops_project_name?: string;
  azuredevops_repo_id?: string;
  // Common fields
  name: string;
  path_with_namespace: string;
  url: string;
  clone_url: string;
  default_branch?: string;
};

export type RepositorySyncResponse = {
  repository_id: number;
  status: string;
  message?: string;
};

export type GitLabProjectDiscovery = {
  gitlab_project_id: number;
  name: string;
  path_with_namespace: string;
  url: string;
  default_branch: string;
  description?: string;
  visibility?: string;
  is_tracked: boolean;
  tracked_repository_id?: number;
};

export type GitLabDiscoveryResponse = {
  group_id: string;
  total_projects: number;
  tracked_count: number;
  untracked_count: number;
  projects: GitLabProjectDiscovery[];
};

export type AzureDevOpsRepositoryDiscovery = {
  azuredevops_project_name: string;
  azuredevops_repo_id: string;
  name: string;
  path_with_namespace: string;
  url: string;
  clone_url: string;
  default_branch: string;
  description?: string;
  is_tracked: boolean;
  tracked_repository_id?: number;
};

export type AzureDevOpsDiscoveryResponse = {
  project_name: string;
  total_repositories: number;
  tracked_count: number;
  untracked_count: number;
  repositories: AzureDevOpsRepositoryDiscovery[];
};

export type BulkRepositoryAddResponse = {
  added_count: number;
  skipped_count: number;
  failed_count: number;
  added_repository_ids: number[];
  errors: string[];
};

export type BulkRepositoryRemoveResponse = {
  removed_count: number;
  failed_count: number;
  errors: string[];
};

export type RepositoryStatsResponse = {
  repository_id: number;
  total_files: number;
  total_symbols: number;
  total_commits: number;
  languages: Record<string, number>;
  symbol_kinds: Record<string, number>;
  size_bytes: number;
  last_sync_duration_seconds: number | null;
  index_health_score: number | null;
  generated_at: string;
};

export type RepositorySyncAttempt = {
  id: number;
  repository_id: number;
  job_id: number | null;
  status: JobStatusEnum;
  triggered_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
};

export type PaginatedResult<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type SearchResult = {
  symbol_id: number;
  file_id: number;
  repository_id: number;
  repository_name: string;
  file_path: string;
  language: LanguageEnum;
  kind: SymbolKindEnum;
  name: string;
  fully_qualified_name: string | null;
  start_line: number;
  end_line: number;
  score: number;
  updated_at: string;
};

export type SearchParams = {
  query: string;
  limit?: number;
  repository_id?: number;
  language?: LanguageEnum;
  symbol_kind?: string;
  hybrid?: boolean;
};

export type SymbolResponse = {
  id: number;
  file_id: number;
  repository_id: number;
  language: LanguageEnum;
  kind: SymbolKindEnum;
  access_modifier: AccessModifierEnum | null;
  name: string;
  fully_qualified_name: string | null;
  start_line: number;
  end_line: number;
  signature: string | null;
  documentation: string | null;
  parameters: Record<string, unknown> | null;
  return_type: string | null;
  parent_symbol_id: number | null;
  created_at: string;
};

export type RelationEdge = {
  id: number;
  relation_type: RelationTypeEnum;
  to_symbol_id: number;
  to_symbol_name: string;
  to_symbol_kind: SymbolKindEnum;
};

export type SymbolWithRelations = SymbolResponse & {
  relations: RelationEdge[];
};

export type FileNode = {
  id: number;
  repository_id: number;
  parent_id: number | null;
  name: string;
  path: string;
  type: FileNodeTypeEnum;
  size_bytes: number;
  language: LanguageEnum | null;
  last_modified: string | null;
  children?: FileNode[];
};

export type FileContentResponse = {
  id: number;
  repository_id: number;
  path: string;
  language: LanguageEnum;
  size_bytes: number;
  line_count: number;
  last_modified: string | null;
  content: string;
};

export type CommitSummary = {
  id: number;
  repository_id: number;
  sha: string;
  message: string;
  author_name: string;
  author_email: string;
  committed_date: string;
};

export type CommitDetail = CommitSummary & {
  parent_sha: string | null;
  files_changed: number;
  insertions: number;
  deletions: number;
  stats?: Record<string, unknown> | null;
};

export type JobResponse = {
  id: number;
  repository_id: number | null;
  job_type: string;
  status: JobStatusEnum;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  retry_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
};

export type JobDetailResponse = JobResponse & {
  celery_task_id: string | null;
  error_message: string | null;
  error_traceback: string | null;
  job_metadata: Record<string, unknown> | null;
};

export type WorkerResponse = {
  id: string;
  hostname: string;
  status: WorkerStatusEnum;
  current_job_id: number | null;
  last_heartbeat_at: string | null;
  queues: string[];
  started_at?: string | null;
};

function isNotFoundError(error: unknown): boolean {
  if (axios.isAxiosError(error)) {
    return error.response?.status === 404;
  }
  return false;
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await api.get<HealthResponse>("/api/v1/health");
  return res.data;
}

export async function getMetricsRaw(): Promise<string> {
  const res = await api.get("/api/v1/metrics", { responseType: "text" });
  return res.data as string;
}

export async function listRepositories(params: {
  skip?: number;
  limit?: number;
} = {}): Promise<PaginatedResult<RepositoryResponse>> {
  const res = await api.get<PaginatedResult<RepositoryResponse>>("/api/v1/repositories", {
    params,
  });
  return res.data;
}

export async function getRepository(repositoryId: number): Promise<RepositoryResponse> {
  const res = await api.get<RepositoryResponse>(`/api/v1/repositories/${repositoryId}`);
  return res.data;
}

export async function createRepository(payload: RepositoryCreatePayload): Promise<RepositoryResponse> {
  const res = await api.post<RepositoryResponse>("/api/v1/repositories", payload);
  return res.data;
}

export async function updateRepository(repositoryId: number, payload: RepositoryUpdatePayload): Promise<RepositoryResponse> {
  try {
    const res = await api.put<RepositoryResponse>(`/api/v1/repositories/${repositoryId}`, payload);
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`Failed to update repository: ${message}`);
    }
    throw error;
  }
}

export async function deleteRepository(repositoryId: number): Promise<void> {
  try {
    await api.delete(`/api/v1/repositories/${repositoryId}`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`Failed to delete repository: ${message}`);
    }
    throw error;
  }
}

export async function syncRepository(repositoryId: number): Promise<RepositorySyncResponse> {
  const res = await api.post<RepositorySyncResponse>(`/api/v1/repositories/${repositoryId}/sync`);
  return res.data;
}

export async function getRepositoryStats(repositoryId: number): Promise<RepositoryStatsResponse | null> {
  try {
    const res = await api.get<RepositoryStatsResponse>(`/api/v1/repositories/${repositoryId}/stats`);
    return res.data;
  } catch (error) {
    if (isNotFoundError(error)) {
      return null;
    }
    throw error;
  }
}

export async function getRepositorySyncHistory(repositoryId: number, params: { limit?: number; offset?: number } = {}): Promise<PaginatedResult<RepositorySyncAttempt>> {
  try {
    const res = await api.get<PaginatedResult<RepositorySyncAttempt>>(
      `/api/v1/repositories/${repositoryId}/sync-history`,
      { params }
    );
    return res.data;
  } catch (error) {
    if (isNotFoundError(error)) {
      return { items: [], total: 0, limit: params.limit ?? 20, offset: params.offset ?? 0 };
    }
    throw error;
  }
}

export async function bulkSyncRepositories(repositoryIds: number[]): Promise<{ jobs_created: number; job_ids: string[]; failed_count?: number; errors?: string[] }> {
  try {
    const res = await api.post<{ jobs_created: number; job_ids: string[]; failed_count: number; errors: string[] }>("/api/v1/repositories/bulk-sync", {
      repository_ids: repositoryIds,
    });
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`Failed to sync repositories: ${message}`);
    }
    throw error;
  }
}

export async function bulkDeleteRepositories(repositoryIds: number[]): Promise<BulkRepositoryRemoveResponse> {
  // Note: Uses POST method instead of DELETE because bulk operations with request bodies
  // should use POST for better HTTP semantics and client/proxy compatibility
  return bulkRemoveRepositories(repositoryIds);
}

export async function discoverGitLabProjects(groupId: string): Promise<GitLabDiscoveryResponse> {
  const res = await api.get<GitLabDiscoveryResponse>(`/api/v1/repositories/discover/${groupId}`);
  return res.data;
}

export async function discoverAzureDevOpsRepositories(projectName: string): Promise<AzureDevOpsDiscoveryResponse> {
  const res = await api.get<AzureDevOpsDiscoveryResponse>(`/api/v1/repositories/discover/azuredevops/${projectName}`);
  return res.data;
}

export async function bulkAddRepositories(repositories: RepositoryCreatePayload[]): Promise<BulkRepositoryAddResponse> {
  const res = await api.post<BulkRepositoryAddResponse>("/api/v1/repositories/bulk-add", {
    repositories,
  });
  return res.data;
}

export async function bulkRemoveRepositories(repositoryIds: number[]): Promise<BulkRepositoryRemoveResponse> {
  const res = await api.post<BulkRepositoryRemoveResponse>("/api/v1/repositories/bulk-remove", {
    repository_ids: repositoryIds,
  });
  return res.data;
}

export async function searchCode(params: SearchParams): Promise<SearchResult[]> {
  const res = await api.get<SearchResult[]>("/api/v1/search", {
    params,
  });
  return res.data;
}

export async function getSymbol(symbolId: number): Promise<SymbolResponse> {
  const res = await api.get<SymbolResponse>(`/api/v1/symbols/${symbolId}`);
  return res.data;
}

export async function getSymbolWithRelations(symbolId: number): Promise<SymbolWithRelations> {
  const res = await api.get<SymbolWithRelations>(`/api/v1/symbols/${symbolId}/relationships`);
  return res.data;
}

export async function listRepositoryFiles(
  repositoryId: number,
  params: { path?: string; depth?: number } = {}
): Promise<FileNode[]> {
  const res = await api.get<FileNode[]>(`/api/v1/repositories/${repositoryId}/files`, { params });
  return res.data;
}

export async function getFile(fileId: number): Promise<FileNode> {
  const res = await api.get<FileNode>(`/api/v1/files/${fileId}`);
  return res.data;
}

export async function getFileContent(fileId: number): Promise<FileContentResponse> {
  const res = await api.get<FileContentResponse>(`/api/v1/files/${fileId}/content`);
  return res.data;
}

export async function listRepositoryCommits(
  repositoryId: number,
  params: { limit?: number; offset?: number } = {}
): Promise<PaginatedResult<CommitSummary>> {
  const res = await api.get<PaginatedResult<CommitSummary>>(`/api/v1/repositories/${repositoryId}/commits`, {
    params,
  });
  return res.data;
}

export async function getCommit(commitId: number): Promise<CommitDetail> {
  const res = await api.get<CommitDetail>(`/api/v1/commits/${commitId}`);
  return res.data;
}

export async function listJobs(params: { status?: JobStatusEnum; limit?: number; offset?: number } = {}): Promise<PaginatedResult<JobResponse>> {
  const res = await api.get<PaginatedResult<JobResponse>>("/api/v1/jobs", { params });
  return res.data;
}

export async function getJob(jobId: number): Promise<JobDetailResponse> {
  const res = await api.get<JobDetailResponse>(`/api/v1/jobs/${jobId}`);
  return res.data;
}

export async function retryJob(jobId: number): Promise<JobDetailResponse> {
  const res = await api.post<JobDetailResponse>(`/api/v1/jobs/${jobId}/retry`);
  return res.data;
}

export async function cancelJob(jobId: number): Promise<void> {
  await api.delete(`/api/v1/jobs/${jobId}`);
}

export async function listWorkers(): Promise<WorkerResponse[]> {
  const res = await api.get<WorkerResponse[]>("/api/v1/workers");
  return res.data;
}

// MCP Server Testing
export type MCPContentItem = {
  type: string;
  text: string;
};

export type MCPToolResponse = {
  content: MCPContentItem[];
  isError: boolean;
};

export async function testMCPSearchCode(params: Record<string, string | number>): Promise<MCPToolResponse> {
  try {
    const res = await api.post<MCPToolResponse>("/api/v1/mcp/tools/search_code", params);
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`MCP search_code failed: ${message}`);
    }
    throw error;
  }
}

export async function testMCPGetSymbolContext(
  symbol_id: number,
  include_relationships: boolean = true
): Promise<MCPToolResponse> {
  try {
    const res = await api.post<MCPToolResponse>("/api/v1/mcp/tools/get_symbol_context", {
      symbol_id,
      include_relationships,
    });
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`MCP get_symbol_context failed: ${message}`);
    }
    throw error;
  }
}

export async function testMCPListRepositories(limit: number = 20): Promise<MCPToolResponse> {
  try {
    const res = await api.post<MCPToolResponse>("/api/v1/mcp/tools/list_repositories", {
      limit,
    });
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`MCP list_repositories failed: ${message}`);
    }
    throw error;
  }
}

export async function callMCPTool(name: string, arguments_dict: Record<string, unknown>): Promise<MCPToolResponse> {
  try {
    const res = await api.post<MCPToolResponse>("/api/v1/mcp/tools/call", {
      name,
      arguments: arguments_dict,
    });
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const message = error.response?.data?.detail || error.message;
      throw new Error(`MCP tool ${name} failed: ${message}`);
    }
    throw error;
  }
}


// Statistics Types

export type SymbolDistribution = {
  kind: string;
  count: number;
};

export type LanguageDistribution = {
  language: string;
  file_count: number;
  size_bytes: number;
};

export type RelationshipDistribution = {
  relation_type: string;
  count: number;
};

export type OverviewStatistics = {
  total_repositories: number;
  total_files: number;
  total_symbols: number;
  total_endpoints: number;
  total_outgoing_calls: number;
  total_published_events: number;
  total_event_subscriptions: number;
  top_languages: LanguageDistribution[];
};

export type RepositoryStatistics = {
  repository_id: number;
  repository_name: string;

  // Basic Counts
  total_files: number;
  total_symbols: number;
  total_endpoints: number;
  total_outgoing_calls: number;
  total_published_events: number;
  total_event_subscriptions: number;
  total_module_summaries: number;

  // Quality Metrics
  files_with_no_symbols: number;
  avg_symbols_per_file: number;

  // Distributions
  symbol_distribution: SymbolDistribution[];
  language_distribution: LanguageDistribution[];
  relationship_distribution: RelationshipDistribution[];
};

// Sample Data Types

export type OutgoingApiCallSample = {
  id: number;
  http_method: string;
  url_pattern: string;
  http_client_library: string | null;
  line_number: number | null;
  file_path: string | null;
};

export type PublishedEventSample = {
  id: number;
  event_type_name: string;
  messaging_library: string | null;
  line_number: number | null;
  file_path: string | null;
};

export type EventSubscriptionSample = {
  id: number;
  event_type_name: string;
  handler_class_name: string | null;
  messaging_library: string | null;
  line_number: number | null;
  file_path: string | null;
};

export type EndpointSample = {
  id: number;
  name: string;
  signature: string | null;
  documentation: string | null;
  line_number: number;
  file_path: string | null;
};

export type ModuleSummarySample = {
  id: number;
  module_name: string;
  module_path: string;
  summary: string;
  file_count: number;
  symbol_count: number;
};

export type RepositorySamples = {
  outgoing_calls: OutgoingApiCallSample[];
  published_events: PublishedEventSample[];
  event_subscriptions: EventSubscriptionSample[];
  endpoints: EndpointSample[];
  module_summaries: ModuleSummarySample[];
};

export async function getOverviewStatistics(): Promise<OverviewStatistics> {
  const res = await api.get<OverviewStatistics>("/api/v1/statistics/overview");
  return res.data;
}

export async function getRepositoryStatistics(repositoryId: number): Promise<RepositoryStatistics> {
  const res = await api.get<RepositoryStatistics>(`/api/v1/statistics/repository/${repositoryId}`);
  return res.data;
}


export async function getRepositorySamples(repositoryId: number): Promise<RepositorySamples> {
  const res = await api.get<RepositorySamples>(`/api/v1/repositories/${repositoryId}/samples`);
  return res.data;
}

// Analysis API Types

export type ServiceAnalysis = {
  id: number;
  name: string;
  service_type: string;
  description: string | null;
  framework_version: string | null;
  entry_points_count: number;
  documentation_path: string | null;
  created_at: string;
};

export type EfEntityAnalysis = {
  id: number;
  entity_name: string;
  namespace: string | null;
  table_name: string | null;
  schema_name: string | null;
  properties_count: number;
  relationships_count: number;
  has_primary_key: boolean;
};

export type IntegrationAnalysis = {
  outgoing_calls_count: number;
  published_events_count: number;
  event_subscriptions_count: number;
  endpoint_links_count: number;
  event_links_count: number;
};

export type IntegrationSummary = {
  summary: IntegrationAnalysis;
  top_outgoing_targets: Array<{ target: string; count: number }>;
  top_event_topics: string[];
};

export type ConfigFinding = {
  id: number;
  config_key: string;
  config_value: string | null;
  environment: string | null;
  is_secret: boolean;
  file_path: string | null;
  line_number: number | null;
};

export type QualityMetric = {
  category: string;
  metric_name: string;
  value: number;
  unit: string;
  status: string; // "good", "warning", "critical"
  details: string | null;
};

export type QualityAnalysis = {
  metrics: QualityMetric[];
  files_with_no_symbols: number;
  files_with_errors: number;
  comment_ratio: number;
};

// Analysis API Functions

export async function getRepositoryServices(repositoryId: number): Promise<ServiceAnalysis[]> {
  const res = await api.get<ServiceAnalysis[]>(`/api/v1/repositories/${repositoryId}/analysis/services`);
  return res.data;
}

export async function getRepositoryEfEntities(repositoryId: number): Promise<EfEntityAnalysis[]> {
  const res = await api.get<EfEntityAnalysis[]>(`/api/v1/repositories/${repositoryId}/analysis/ef-entities`);
  return res.data;
}

export async function getRepositoryIntegrations(repositoryId: number): Promise<IntegrationSummary> {
  const res = await api.get<IntegrationSummary>(`/api/v1/repositories/${repositoryId}/analysis/integrations`);
  return res.data;
}

export async function getRepositoryConfigFindings(repositoryId: number): Promise<ConfigFinding[]> {
  const res = await api.get<ConfigFinding[]>(`/api/v1/repositories/${repositoryId}/analysis/config-findings`);
  return res.data;
}

export async function getRepositoryQualityMetrics(repositoryId: number): Promise<QualityAnalysis> {
  const res = await api.get<QualityAnalysis>(`/api/v1/repositories/${repositoryId}/analysis/quality-metrics`);
  return res.data;
}
