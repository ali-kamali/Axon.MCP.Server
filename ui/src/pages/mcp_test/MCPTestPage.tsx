import { FormEvent, useMemo, useState } from "react";
import {
  callMCPTool,
  type MCPToolResponse,
} from "../../services/api";
import { LanguageEnum, SymbolKindEnum } from "../../types/enums";
import styles from "./MCPTestPage.module.css";

type ToolField = {
  name: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "json";
  required?: boolean;
  placeholder?: string;
  hint?: string;
  options?: { label: string; value: string | number }[];
  defaultValue?: string | number | boolean;
};

type ToolDefinition = {
  name: string;
  description: string;
  icon: string;
  fields: ToolField[];
};

const TOOLS: ToolDefinition[] = [
  {
    name: "search_code",
    description: "Search for code symbols across repositories",
    icon: "🔍",
    fields: [
      { name: "query", label: "Query", type: "text", required: true, placeholder: "e.g., authentication" },
      { name: "limit", label: "Limit", type: "number", defaultValue: 10 },
      { name: "repository_name", label: "Repository Name", type: "text" },
      {
        name: "language",
        label: "Language",
        type: "select",
        options: [{ label: "All", value: "" }, ...Object.values(LanguageEnum).map(l => ({ label: l, value: l }))]
      },
      {
        name: "symbol_kind",
        label: "Symbol Kind",
        type: "select",
        options: [{ label: "All", value: "" }, ...Object.values(SymbolKindEnum).map(k => ({ label: k, value: k }))]
      },
    ],
  },
  {
    name: "get_symbol_context",
    description: "Get detailed context for a specific symbol",
    icon: "📄",
    fields: [
      { name: "symbol_id", label: "Symbol ID", type: "number", required: true },
      { name: "include_relationships", label: "Include Relationships", type: "boolean", defaultValue: true },
      { name: "depth", label: "Depth", type: "number", defaultValue: 0, hint: "0=symbol only, 1=direct, 2+=recursive" },
      {
        name: "direction",
        label: "Direction",
        type: "select",
        defaultValue: "downstream",
        options: [
          { label: "Downstream (calls)", value: "downstream" },
          { label: "Upstream (called by)", value: "upstream" },
          { label: "Both", value: "both" },
        ]
      },
    ],
  },
  {
    name: "list_repositories",
    description: "List available repositories",
    icon: "📚",
    fields: [
      { name: "limit", label: "Limit", type: "number", defaultValue: 20 },
    ],
  },
  {
    name: "search_documentation",
    description: "Search markdown documentation files",
    icon: "📖",
    fields: [
      { name: "query", label: "Query", type: "text", required: true },
      { name: "repository_id", label: "Repository ID", type: "number" },
      { name: "doc_type", label: "Doc Type", type: "text", placeholder: "readme, guide, etc." },
      { name: "limit", label: "Limit", type: "number", defaultValue: 10 },
    ],
  },
  {
    name: "search_configuration",
    description: "Search configuration settings",
    icon: "⚙️",
    fields: [
      { name: "key_pattern", label: "Key Pattern", type: "text", required: true, placeholder: "e.g. Database:*" },
      { name: "repository_id", label: "Repository ID", type: "number" },
      { name: "environment", label: "Environment", type: "text" },
      { name: "limit", label: "Limit", type: "number", defaultValue: 20 },
    ],
  },
  {
    name: "list_dependencies",
    description: "List package dependencies",
    icon: "📦",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "dependency_type", label: "Type", type: "text", placeholder: "npm, nuget, pip" },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
  {
    name: "get_file_content",
    description: "Read file content",
    icon: "📝",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "file_path", label: "File Path", type: "text", required: true },
      { name: "start_line", label: "Start Line", type: "number" },
      { name: "end_line", label: "End Line", type: "number" },
    ],
  },
  {
    name: "find_usages",
    description: "Find symbol usages",
    icon: "🔎",
    fields: [
      { name: "symbol_id", label: "Symbol ID", type: "number", required: true },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
  {
    name: "find_implementations",
    description: "Find interface implementations",
    icon: "🧩",
    fields: [
      { name: "interface_id", label: "Interface ID", type: "number", required: true },
    ],
  },
  {
    name: "find_references",
    description: "Find all references",
    icon: "🔗",
    fields: [
      { name: "symbol_id", label: "Symbol ID", type: "number", required: true },
      { name: "reference_type", label: "Type", type: "text", placeholder: "calls, inherits, implements" },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
  {
    name: "get_file_tree",
    description: "Get directory tree",
    icon: "🌳",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "path", label: "Path", type: "text", placeholder: "Root if empty" },
      { name: "depth", label: "Depth", type: "number", defaultValue: 3 },
    ],
  },
  {
    name: "list_symbols_in_file",
    description: "List symbols in file",
    icon: "📋",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "file_path", label: "File Path", type: "text", required: true },
    ],
  },
  {
    name: "find_api_endpoints",
    description: "Find API endpoints",
    icon: "🌐",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "http_method", label: "Method", type: "text", placeholder: "GET, POST..." },
      { name: "route_pattern", label: "Route Pattern", type: "text" },
    ],
  },
  {
    name: "get_call_hierarchy",
    description: "Get call hierarchy",
    icon: "📶",
    fields: [
      { name: "symbol_id", label: "Symbol ID", type: "number", required: true },
      {
        name: "direction",
        label: "Direction",
        type: "select",
        defaultValue: "outbound",
        options: [{ label: "Outbound (calls)", value: "outbound" }, { label: "Inbound (called by)", value: "inbound" }]
      },
      { name: "depth", label: "Depth", type: "number", defaultValue: 3 },
    ],
  },
  {
    name: "find_callers",
    description: "Find callers",
    icon: "⬅️",
    fields: [
      { name: "symbol_id", label: "Symbol ID", type: "number", required: true },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
  {
    name: "find_callees",
    description: "Find callees",
    icon: "➡️",
    fields: [
      { name: "symbol_id", label: "Symbol ID", type: "number", required: true },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
  {
    name: "analyze_architecture",
    description: "Analyze architecture",
    icon: "🏗️",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
    ],
  },
  {
    name: "search_by_path",
    description: "Search files by path",
    icon: "📂",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "path_pattern", label: "Pattern", type: "text", required: true, placeholder: "**/*.ts" },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
  {
    name: "trace_request_flow",
    description: "Trace request flow",
    icon: "〰️",
    fields: [
      { name: "endpoint", label: "Endpoint", type: "text", required: true, placeholder: "POST /api/users" },
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
    ],
  },
  {
    name: "get_project_map",
    description: "Get project map",
    icon: "🗺️",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "max_depth", label: "Max Depth", type: "number", defaultValue: 2 },
    ],
  },
  {
    name: "get_module_summary",
    description: "Get module summary",
    icon: "📑",
    fields: [
      { name: "repository_id", label: "Repository ID", type: "number", required: true },
      { name: "module_path", label: "Module Path", type: "text", required: true },
      { name: "generate_if_missing", label: "Generate if missing", type: "boolean", defaultValue: true },
    ],
  },
  {
    name: "query_codebase_structure",
    description: "Query codebase structure",
    icon: "🧠",
    fields: [
      { name: "query", label: "Query", type: "text", required: true },
      { name: "repository_id", label: "Repository ID", type: "number" },
      { name: "limit", label: "Limit", type: "number", defaultValue: 50 },
    ],
  },
];

export default function MCPTestPage() {
  const [selectedToolName, setSelectedToolName] = useState<string>(TOOLS[0].name);
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [response, setResponse] = useState<MCPToolResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedTool = useMemo(() => TOOLS.find(t => t.name === selectedToolName) || TOOLS[0], [selectedToolName]);

  const handleToolChange = (name: string) => {
    setSelectedToolName(name);
    setFormValues({});
    setResponse(null);
    setError(null);
  };

  const handleInputChange = (field: string, value: any) => {
    setFormValues(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    try {
      setLoading(true);
      setError(null);

      // Prepare arguments based on field types
      const args: Record<string, any> = {};

      for (const field of selectedTool.fields) {
        const rawValue = formValues[field.name];

        // Use default value if empty and not required
        if (rawValue === undefined || rawValue === "") {
          if (field.defaultValue !== undefined) {
            args[field.name] = field.defaultValue;
          } else if (field.required) {
            throw new Error(`Field '${field.label}' is required`);
          }
          continue;
        }

        // Type conversion
        if (field.type === "number") {
          const num = Number(rawValue);
          if (Number.isNaN(num)) {
            throw new Error(`Field '${field.label}' must be a number`);
          }
          args[field.name] = num;
        } else if (field.type === "boolean") {
          args[field.name] = Boolean(rawValue);
        } else {
          args[field.name] = rawValue;
        }
      }

      const result = await callMCPTool(selectedTool.name, args);
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tool execution failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.mcp_test_page}>
      <div className={styles.header}>
        <h1 className={styles.title}>MCP Server Tester</h1>
        <p className={styles.subtitle}>
          Test all available MCP tools directly from the UI.
        </p>
      </div>

      <div className={styles.content}>
        <aside className={styles.tool_selector}>
          <h2 className={styles.section_title}>Available Tools</h2>
          <div className={styles.tool_list}>
            {TOOLS.map(tool => (
              <button
                key={tool.name}
                className={`${styles.tool_button} ${selectedToolName === tool.name ? styles.tool_button_active : ""
                  }`}
                onClick={() => handleToolChange(tool.name)}
              >
                <div className={styles.tool_icon}>{tool.icon}</div>
                <div className={styles.tool_info}>
                  <div className={styles.tool_name}>{tool.name}</div>
                  <div className={styles.tool_description}>
                    {tool.description}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <main className={styles.tool_workspace}>
          <div className={styles.tool_header}>
            <h2 className={styles.tool_title}>Tool: {selectedTool.name}</h2>
          </div>

          <form className={styles.tool_form} onSubmit={handleSubmit}>
            <div className={styles.form_row_dynamic}>
              {selectedTool.fields.map(field => (
                <div key={field.name} className={styles.form_group}>
                  {field.type === "boolean" ? (
                    <label className={styles.checkbox_label}>
                      <input
                        type="checkbox"
                        checked={formValues[field.name] ?? field.defaultValue ?? false}
                        onChange={(e) => handleInputChange(field.name, e.target.checked)}
                      />
                      {field.label}
                    </label>
                  ) : (
                    <>
                      <label className={styles.form_label} htmlFor={field.name}>
                        {field.label} {field.required && <span className={styles.required}>*</span>}
                      </label>
                      {field.type === "select" ? (
                        <select
                          id={field.name}
                          className={styles.form_select}
                          value={formValues[field.name] ?? field.defaultValue ?? ""}
                          onChange={(e) => handleInputChange(field.name, e.target.value)}
                        >
                          {field.options?.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          id={field.name}
                          type={field.type === "number" ? "number" : "text"}
                          className={styles.form_input}
                          value={formValues[field.name] ?? ""}
                          onChange={(e) => handleInputChange(field.name, e.target.value)}
                          placeholder={field.placeholder}
                          required={field.required}
                        />
                      )}
                      {field.hint && <span className={styles.form_hint}>{field.hint}</span>}
                    </>
                  )}
                </div>
              ))}
            </div>

            <button className={styles.submit_button} type="submit" disabled={loading}>
              {loading ? "Executing..." : `Call ${selectedTool.name}`}
            </button>
          </form>

          {error && (
            <div className={styles.error_box}>
              <div className={styles.error_header}>
                <strong>❌ Error</strong>
                <button className={styles.dismiss_button} onClick={() => setError(null)}>
                  Dismiss
                </button>
              </div>
              <p className={styles.error_message}>{error}</p>
            </div>
          )}

          {response && (
            <div className={styles.response_container}>
              <div className={styles.response_header}>
                <h3 className={styles.response_title}>
                  {response.isError ? "❌ Error Response" : "✅ MCP Response"}
                </h3>
                <span
                  className={`${styles.status_badge} ${response.isError ? styles.status_error : styles.status_success
                    }`}
                >
                  {response.isError ? "Error" : "Success"}
                </span>
              </div>

              <div className={styles.response_content}>
                {response.content && response.content.length > 0 ? (
                  response.content.map((item, index) => (
                    <div key={index} className={styles.content_item}>
                      <div className={styles.content_type}>Type: {item.type}</div>
                      <pre className={styles.content_text}>{item.text}</pre>
                    </div>
                  ))
                ) : (
                  <p className={styles.empty_response}>No content in response</p>
                )}
              </div>

              <div className={styles.raw_response}>
                <details>
                  <summary className={styles.raw_response_toggle}>
                    View Raw JSON Response
                  </summary>
                  <pre className={styles.raw_json}>{JSON.stringify(response, null, 2)}</pre>
                </details>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}


