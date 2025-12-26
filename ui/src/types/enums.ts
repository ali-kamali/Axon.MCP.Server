// Mirrors backend enums; no raw strings used in UI

export enum EnvironmentEnum {
  development = "development",
  staging = "staging",
  production = "production",
}

export enum RepositoryStatusEnum {
  pending = "PENDING",
  cloning = "CLONING",
  parsing = "PARSING",
  extracting = "EXTRACTING",
  embedding = "EMBEDDING",
  completed = "COMPLETED",
  failed = "FAILED",
}

export enum JobStatusEnum {
  pending = "PENDING",
  running = "RUNNING",
  completed = "COMPLETED",
  failed = "FAILED",
  cancelled = "CANCELLED",
  retrying = "RETRYING",
}

export enum LanguageEnum {
  csharp = "CSHARP",
  javascript = "JAVASCRIPT",
  typescript = "TYPESCRIPT",
  vue = "VUE",
  python = "PYTHON",
  go = "GO",
  java = "JAVA",
  markdown = "MARKDOWN",
  sql = "SQL",
  unknown = "UNKNOWN",
}

export enum SymbolKindEnum {
  function = "FUNCTION",
  method = "METHOD",
  class = "CLASS",
  interface = "INTERFACE",
  struct = "STRUCT",
  enum = "ENUM",
  variable = "VARIABLE",
  constant = "CONSTANT",
  property = "PROPERTY",
  namespace = "NAMESPACE",
  module = "MODULE",
  type_alias = "TYPE_ALIAS",
  document_section = "DOCUMENT_SECTION",
  code_example = "CODE_EXAMPLE",
}

export enum RelationTypeEnum {
  calls = "CALLS",
  imports = "IMPORTS",
  exports = "EXPORTS",
  inherits = "INHERITS",
  implements = "IMPLEMENTS",
  uses = "USES",
  contains = "CONTAINS",
}

export enum AccessModifierEnum {
  public = "PUBLIC",
  private = "PRIVATE",
  protected = "PROTECTED",
  internal = "INTERNAL",
  protected_internal = "PROTECTED_INTERNAL",
  private_protected = "PRIVATE_PROTECTED",
}

export enum FileNodeTypeEnum {
  directory = "directory",
  file = "file",
}

export enum WorkerStatusEnum {
  online = "ONLINE",
  offline = "OFFLINE",
  busy = "BUSY",
  starting = "STARTING",
  unknown = "UNKNOWN",
}

export enum SourceControlProviderEnum {
  gitlab = "GITLAB",
  azuredevops = "AZUREDEVOPS",
}


