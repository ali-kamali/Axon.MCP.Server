using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.MSBuild;
using Newtonsoft.Json;

namespace RoslynAnalyzer
{
    class Program
    {
        // Global state for persistent process (LEGACY - To be deprecated)
        static class GlobalState
        {
            public static MSBuildWorkspace? Workspace { get; set; }
            public static Solution? CurrentSolution { get; set; }
            public static ProjectId? CurrentProjectId { get; set; }
            public static string? CurrentProjectPath { get; set; }
        }

        // NEW: Stateless Project Cache
        private static readonly Dictionary<string, (Project Project, DateTime LastAccess)> _projectCache 
            = new Dictionary<string, (Project, DateTime)>();
        private static readonly object _cacheLock = new object();
        private static readonly int _maxCacheSize = 10;
        private static readonly TimeSpan _cacheExpiry = TimeSpan.FromMinutes(30);

        static async Task Main(string[] args)
        {
            try
            {
                // Register MSBuild defaults BEFORE using any MSBuild types
                Microsoft.Build.Locator.MSBuildLocator.RegisterDefaults();

                AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
                {
                    var msg = $"[CRITICAL] Unhandled Exception: {e.ExceptionObject}";
                    Console.Error.WriteLine(msg);
                    try { File.AppendAllText("roslyn_crash.log", msg + Environment.NewLine); } catch { }
                };
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"Failed to register MSBuild defaults: {ex.Message}");
            }

            await RunAsync(args);
        }

        // Helper to load project statelessly with caching
        static async Task<Project> GetOrLoadProject(string projectPath)
        {
            // Normalize path
            projectPath = Path.GetFullPath(projectPath);

            IDisposable? workspaceToDispose = null;
            
            lock (_cacheLock)
            {
                if (_projectCache.TryGetValue(projectPath, out var cached))
                {
                    if (DateTime.UtcNow - cached.LastAccess < _cacheExpiry)
                    {
                        // Update access time (copy struct with new time)
                        _projectCache[projectPath] = (cached.Project, DateTime.UtcNow);
                        return cached.Project;
                    }
                    else
                    {
                        // Extract workspace reference for disposal outside lock
                        workspaceToDispose = cached.Project.Solution.Workspace as IDisposable;
                        _projectCache.Remove(projectPath);
                    }
                }
            }
            
            // Dispose outside lock to avoid blocking other threads
            if (workspaceToDispose != null)
            {
                try 
                {
                    workspaceToDispose.Dispose();
                }
                catch 
                { 
                    // Best effort disposal
                }
            }

            // Load project (outside lock)
            // Note: We create a fresh Workspace for each project to avoid pollution? 
            // Or reuse one? MSBuildWorkspace is heavy?
            // MSBuildWorkspace is designed to handle multiple projects, but isolation is safer for us.
            // Let's create a new workspace per project for true statelessness, 
            // OR use a shared cache workspace. 
            // Creating new workspace per project is safer against side-effects but uses more memory.
            // Given we cache only 10, maybe okay?
            // Actually, MSBuildWorkspace.Create() is the way.
            
            var properties = new Dictionary<string, string>
            {
                { "Configuration", "Release" },
                { "NuGetAudit", "false" },
                { "NoWarn", "NU1901;NU1902;NU1903;NU1904;NU1701" },
                { "TreatWarningsAsErrors", "false" }
            };

            var workspace = MSBuildWorkspace.Create(properties);
            workspace.LoadMetadataForReferencedProjects = true; // deeper analysis
            
            var project = await workspace.OpenProjectAsync(projectPath);

            lock (_cacheLock)
            {
                // Evict if full
                if (_projectCache.Count >= _maxCacheSize && !_projectCache.ContainsKey(projectPath))
                {
                    var oldest = _projectCache.OrderBy(kv => kv.Value.LastAccess).First();
                    
                    // Dispose workspace of evicted project to prevent memory leak
                    try
                    {
                        if (oldest.Value.Project.Solution.Workspace is IDisposable disposable)
                        {
                            disposable.Dispose();
                        }
                    }
                    catch
                    {
                        // Best effort disposal
                    }
                    
                    _projectCache.Remove(oldest.Key);
                }
                
                _projectCache[projectPath] = (project, DateTime.UtcNow);
            }
            
            return project;
        }

        static async Task RunAsync(string[] args)
        {
            try
            {
                // Initialize MSBuild workspace
                // This requires valid MSBuild tools (installed via .NET SDK)
                var properties = new Dictionary<string, string>
                {
                    // Ensure we use the current configuration
                    { "Configuration", "Release" },
                    // Disable NuGet audit to prevent vulnerability warnings from failing the build
                    { "NuGetAudit", "false" },
                    // Explicitly suppress vulnerability warnings
                    { "NoWarn", "NU1901;NU1902;NU1903;NU1904;NU1701" },
                    // Ensure warnings are not treated as errors
                    { "TreatWarningsAsErrors", "false" },
                    { "WarningsAsErrors", "false" }
                };

                GlobalState.Workspace = MSBuildWorkspace.Create(properties);
                GlobalState.Workspace.WorkspaceFailed += (s, e) => 
                {
                    // Log workspace failures to stderr but don't crash
                    var kind = e.Diagnostic.Kind.ToString();
                    Console.Error.WriteLine($"Workspace {kind}: {e.Diagnostic.Message}");
                };

                // Persistent loop: read line -> process -> write line
                string? line;
                while ((line = await Console.In.ReadLineAsync()) != null)
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;

                    try
                    {
                        var request = JsonConvert.DeserializeObject<AnalysisRequest>(line);
                        if (request == null)
                        {
                            WriteError("Invalid JSON input");
                            continue;
                        }


                        object result;
                        switch (request.Operation)
                        {
                            case "analyze":
                                result = await AnalyzeFile(request);
                                break;
                            case "analyze_file": // NEW Stateless command
                                result = await AnalyzeFileStateless(request);
                                break;
                            case "resolve_reference":
                                // If ProjectPath present, use stateless
                                if (!string.IsNullOrEmpty(request.ProjectPath))
                                    result = await ResolveReferenceStateless(request);
                                else
                                    result = await ResolveReference(request); // Legacy
                                break;
                            case "get_inheritance":
                                result = await GetInheritanceChain(request);
                                break;
                            case "open_project":
                                result = await OpenProject(request);
                                break;
                            case "open_solution":
                                result = await OpenSolution(request);
                                break;
                            case "analyze_ef_entities":
                                result = await AnalyzeEfEntitiesStateless(request);
                                break;
                            case "ping":
                                result = new { success = true, message = "pong" };
                                break;
                            case "shutdown":
                                WriteError("Shutting down"); // Ack
                                return;
                            default:
                                result = new { success = false, error = $"Unknown operation: {request.Operation}" };
                                break;
                        }


                        Console.WriteLine(JsonConvert.SerializeObject(result, Formatting.None));
                    }
                    catch (Exception ex)
                    {
                        WriteError($"Request processing error: {ex.Message}");
                    }
                }
            }
            catch (Exception ex)
            {
                WriteError($"Fatal error: {ex.Message}");
            }
        }

        // --- Stateless Operation Handlers ---

        static async Task<object> AnalyzeFileStateless(AnalysisRequest request)
        {
            var projectPath = request.ProjectPath;
            var filePath = request.FilePath;
            var code = request.Code;

            if (string.IsNullOrEmpty(projectPath))
            {
               return new { success = false, error = "project_path required for stateless analysis" };
            }

            try
            {
                var project = await GetOrLoadProject(projectPath);
                
                // Allow fuzzy path matching because Docker paths might differ slightly from .csproj paths
                // Normalize both
                var targetPath = Path.GetFullPath(filePath);
                
                var document = project.Documents.FirstOrDefault(d => 
                    string.Equals(Path.GetFullPath(d.FilePath), targetPath, StringComparison.OrdinalIgnoreCase));

                if (document == null)
                {
                     // Ad-hoc fallback requested? 
                     // For now, return explicit error so Python knows to try fallback or fail
                     return new { 
                         success = false, 
                         error = "file_not_in_project",
                         file_path = filePath,
                         project_path = projectPath,
                         using_adhoc = true 
                     };
                }

                if (!string.IsNullOrEmpty(code))
                {
                    document = document.WithText(Microsoft.CodeAnalysis.Text.SourceText.From(code));
                }

                var semanticModel = await document.GetSemanticModelAsync();
                var root = await document.GetSyntaxRootAsync();
                if (semanticModel == null || root == null) return new { success = false, error = "Failed to get semantic model or syntax root" };

                var symbols = ExtractSymbolsFromModel(semanticModel, root); 
                
                return new { success = true, file_path = filePath, symbols = symbols };
            }
            catch (Exception ex)
            {
                return new { success = false, error = $"Stateless analysis failed: {ex.Message}" };
            }
        }

        static async Task<object> ResolveReferenceStateless(AnalysisRequest request)
        {
            try 
            {
                var project = await GetOrLoadProject(request.ProjectPath);
                var document = project.Documents.FirstOrDefault(d => 
                    string.Equals(Path.GetFullPath(d.FilePath), Path.GetFullPath(request.FilePath), StringComparison.OrdinalIgnoreCase));

                if (document == null) return new { success = false, error = "File not found in project" };

                if (!string.IsNullOrEmpty(request.Code))
                {
                    document = document.WithText(Microsoft.CodeAnalysis.Text.SourceText.From(request.Code));
                }

                var semanticModel = await document.GetSemanticModelAsync();
                var root = await document.GetSyntaxRootAsync();
                var node = root.FindToken(request.Position).Parent;

                ISymbol symbol = null;
                if (node != null)
                {
                    symbol = semanticModel.GetSymbolInfo(node).Symbol;
                }

                if (symbol == null) return new { success = false, error = "Symbol not resolved" };

                return FormatSymbolResult(symbol);
            }
            catch (Exception ex)
            {
                return new { success = false, error = $"Stateless resolution failed: {ex.Message}" };
            }
        }

        static List<object> ExtractSymbolsFromModel(SemanticModel semanticModel, SyntaxNode root)
        {
            var symbols = new List<object>();
            foreach (var node in root.DescendantNodes())
            {
                ISymbol? symbol = null;
                if (node is ClassDeclarationSyntax c) symbol = semanticModel.GetDeclaredSymbol(c);
                else if (node is InterfaceDeclarationSyntax i) symbol = semanticModel.GetDeclaredSymbol(i);
                else if (node is MethodDeclarationSyntax m) symbol = semanticModel.GetDeclaredSymbol(m);
                else if (node is PropertyDeclarationSyntax p) symbol = semanticModel.GetDeclaredSymbol(p);

                if (symbol != null)
                {
                     // Use the existing ExtractSymbolInfo(ISymbol) method
                     symbols.Add(ExtractSymbolInfo(symbol));
                }
            }
            return symbols;
        }

        // --- Operation Handlers ---

        static async Task<object> OpenProject(AnalysisRequest request)
        {
            try
            {
                var projectPath = request.FilePath;
                if (!File.Exists(projectPath))
                {
                    return new { success = false, error = $"Project file not found: {projectPath}" };
                }

                // If already open, skip
                if (GlobalState.CurrentProjectPath == projectPath && GlobalState.CurrentSolution != null)
                {
                   return new { success = true, message = "Project already open" };
                }

                if (GlobalState.Workspace == null) throw new InvalidOperationException("Workspace not initialized");

                // Close current solution logic if needed (MSBuildWorkspace usually handles one solution/project set at a time better if we clear)
                GlobalState.Workspace.CloseSolution();

                var project = await GlobalState.Workspace.OpenProjectAsync(projectPath);
                GlobalState.CurrentSolution = GlobalState.Workspace.CurrentSolution;
                GlobalState.CurrentProjectId = project.Id;
                GlobalState.CurrentProjectPath = projectPath;

                // Force GC to clear previous project's memory
                GC.Collect();
                GC.WaitForPendingFinalizers();

                var result = new 
                { 
                    success = true, 
                    message = $"Project opened: {project.Name}",
                    project_name = project.Name,
                    document_count = project.Documents.Count() 
                };
                
                // Debug logging:
                Console.Error.WriteLine($"[DEBUG] Opened project {project.Name} with {project.Documents.Count()} documents.");
                var sampleDocs = project.Documents.Take(5).Select(d => d.FilePath).ToList();
                foreach (var doc in sampleDocs)
                {
                   Console.Error.WriteLine($"[DEBUG] Loaded Doc Path: {doc}");
                }

                return result;
            }
            catch (Exception ex)
            {
                return new { success = false, error = $"Failed to open project: {ex.Message}" };
            }
        }

        static async Task<object> OpenSolution(AnalysisRequest request)
        {
            try
            {
                var solutionPath = request.FilePath;
                if (!File.Exists(solutionPath))
                {
                    return new { success = false, error = $"Solution file not found: {solutionPath}" };
                }
                
                if (GlobalState.Workspace == null) throw new InvalidOperationException("Workspace not initialized");

                GlobalState.Workspace.CloseSolution();

                var solution = await GlobalState.Workspace.OpenSolutionAsync(solutionPath);
                GlobalState.CurrentSolution = solution;
                GlobalState.CurrentProjectPath = solutionPath; // Tracking solution path here

                return new 
                { 
                    success = true, 
                    message = $"Solution opened", 
                    project_count = solution.Projects.Count() 
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = $"Failed to open solution: {ex.Message}" };
            }
        }

        static async Task<object> ResolveReference(AnalysisRequest request)
        {
            try
            {
                // Try to use loaded workspace first
                if (GlobalState.CurrentSolution != null)
                {
                    var result = await ResolveWithWorkspace(request);
                    if (result != null) return result;
                }

                // Fallback to ad-hoc analysis if workspace lookup fails or not initialized
                return await ResolveAdHoc(request);
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        static async Task<object?> ResolveWithWorkspace(AnalysisRequest request)
        {
            // Find document in current solution
            // request.FilePath is the absolute path to the C# file
            var solution = GlobalState.CurrentSolution;
            if (solution == null) return null;

            Document? doc = null;
            var requestPath = request.FilePath;
            
            if (string.IsNullOrEmpty(requestPath))
            {
                return null;
            }

            // Normalize request path to absolute path once
            string absRequestPath;
            try
            {
                absRequestPath = Path.GetFullPath(requestPath);
            }
            catch
            {
                // If we can't get full path, keep original
                absRequestPath = requestPath;
            }
            
            // OPTIMIZATION: Search the currently loaded project first
            // Since _ensure_project_loaded() was called before this, the file likely belongs to CurrentProject
            // This is O(1) vs O(N) if we search all projects
            List<ProjectId> projectsToSearch = new List<ProjectId>();
            
            if (GlobalState.CurrentProjectId != null)
            {
                // Priority 1: Search the project we just loaded for this file
                projectsToSearch.Add(GlobalState.CurrentProjectId);
            }
            
            // Priority 2: Add all other projects as fallback
            foreach (var projectId in solution.ProjectIds)
            {
                if (projectId != GlobalState.CurrentProjectId)
                {
                    projectsToSearch.Add(projectId);
                }
            }
            
            // Search projects in priority order
            foreach (var projectId in projectsToSearch)
            {
                var project = solution.GetProject(projectId);
                if (project == null) continue;

                // Strategy 0: Exact Absolute Path Match (The most robust)
                // This handles cases where request is partial/relative but resolves to same file
                var absDocId = project.Documents.FirstOrDefault(d => 
                {
                    if (d.FilePath == null) return false;
                    try
                    {
                        var absDocPath = Path.GetFullPath(d.FilePath);
                        return string.Equals(absDocPath, absRequestPath, StringComparison.OrdinalIgnoreCase);
                    }
                    catch
                    {
                        return false;
                    }
                })?.Id;

                if (absDocId != null)
                {
                    doc = project.GetDocument(absDocId);
                    break;
                }

                // Strategy 1: Exact match (case-insensitive) as-is
                var docId = project.Documents.FirstOrDefault(d => 
                {
                    if (d.FilePath == null) return false;
                    return string.Equals(d.FilePath, requestPath, StringComparison.OrdinalIgnoreCase);
                })?.Id;
                
                if (docId != null)
                {
                    doc = project.GetDocument(docId);
                    break;
                }
                
                // Strategy 2: Normalized path comparison (forward slashes, trimmed)
                // Useful when paths differ only by separator style
                var requestPathNormalized = requestPath.Replace("\\", "/").TrimEnd('/');
                docId = project.Documents.FirstOrDefault(d => 
                {
                    if (d.FilePath == null) return false;
                    var docPath = d.FilePath.Replace("\\", "/").TrimEnd('/');
                    return string.Equals(docPath, requestPathNormalized, StringComparison.OrdinalIgnoreCase);
                })?.Id;
                
                if (docId != null)
                {
                    doc = project.GetDocument(docId);
                    break;
                }
                
                // Strategy 3: Try relative path from project directory
                if (project.FilePath != null)
                {
                    try
                    {
                        var projectDir = Path.GetDirectoryName(project.FilePath);
                        if (projectDir != null)
                        {
                            // Normalize paths for cross-platform comparison
                            var normalizedProjectDir = Path.GetFullPath(projectDir).Replace("\\", "/").TrimEnd('/');
                            // reuse absRequestPath which is already resolved
                            var normalizedRequestPath = absRequestPath.Replace("\\", "/").TrimEnd('/');
                            
                            // Check if request path is under project directory
                            if (normalizedRequestPath.StartsWith(normalizedProjectDir, StringComparison.OrdinalIgnoreCase))
                            {
                                var relativePath = Path.GetRelativePath(projectDir, absRequestPath);
                                
                                docId = project.Documents.FirstOrDefault(d =>
                                {
                                    if (d.FilePath == null) return false;
                                    
                                    try
                                    {
                                        var docRelativePath = Path.GetRelativePath(projectDir, d.FilePath);
                                        // Normalize relative paths for comparison (handle \ vs /)
                                        var normalizedDocRelative = docRelativePath.Replace("\\", "/");
                                        var normalizedRequestRelative = relativePath.Replace("\\", "/");
                                        
                                        return string.Equals(normalizedDocRelative, normalizedRequestRelative, StringComparison.OrdinalIgnoreCase);
                                    }
                                    catch
                                    {
                                        return false;
                                    }
                                })?.Id;
                                
                                if (docId != null)
                                {
                                    doc = project.GetDocument(docId);
                                    break;
                                }
                            }
                        }
                    }
                    catch
                    {
                        // Path.GetFullPath or Path.GetRelativePath can throw on invalid paths
                        // Continue to next strategy
                    }
                }
                
                // Strategy 4: Try filename-only match (last resort, but check for uniqueness)
                var requestFileName = Path.GetFileName(requestPath);
                var matchingDocs = project.Documents.Where(d =>
                {
                    if (d.FilePath == null) return false;
                    var docFileName = Path.GetFileName(d.FilePath);
                    return string.Equals(docFileName, requestFileName, StringComparison.OrdinalIgnoreCase);
                }).ToList();
                
                if (matchingDocs.Count == 1)
                {
                    // Only use filename match if it's unique within the project
                    doc = matchingDocs[0];
                    break;
                }
            }

            // Strategy 4: Injection into Current Project (The "Better AdHoc")
            // If we haven't found the document in any project, but we have a CurrentProject context,
            // inject the file into that project so we can analyze it with dependencies.
            if (doc == null && GlobalState.CurrentProjectId != null)
            {
                var project = solution.GetProject(GlobalState.CurrentProjectId);
                if (project != null)
                {
                    string fileContent = request.Code;
                    if (string.IsNullOrEmpty(fileContent) && File.Exists(absRequestPath))
                    {
                         try { fileContent = File.ReadAllText(absRequestPath); } catch {}
                    }

                    if (!string.IsNullOrEmpty(fileContent))
                    {
                         Console.Error.WriteLine($"[DEBUG] Strategy 4: Injecting document {Path.GetFileName(absRequestPath)} into project {project.Name} to retain references.");
                         doc = project.AddDocument(Path.GetFileName(absRequestPath), fileContent, filePath: absRequestPath);
                    }
                }
            }

            if (doc == null)
            {
                // Document not found in loaded workspace - log for diagnostics
                Console.Error.WriteLine($"[DEBUG] Document not found in workspace: {requestPath}");
                Console.Error.WriteLine($"[DEBUG] Resolved request path: {absRequestPath}");
                Console.Error.WriteLine($"[DEBUG] Loaded projects: {solution.ProjectIds.Count}");
                Console.Error.WriteLine($"[DEBUG] Current project: {GlobalState.CurrentProjectId}");
                
                // Log project info for debugging (limit to first 10 docs to avoid spam)
                foreach (var projectId in solution.ProjectIds)
                {
                    var project = solution.GetProject(projectId);
                    if (project != null)
                    {
                        Console.Error.WriteLine($"[DEBUG]   Project: {project.Name}, Path: {project.FilePath}, Documents: {project.Documents.Count()}");
                        // Debug: print first few doc paths
                        foreach(var d in project.Documents.Take(3)) {
                             Console.Error.WriteLine($"[DEBUG]     - {d.FilePath}");
                        }
                    }
                }
                
                return null; 
            }

            // Log successful document resolution with context
            var wasInCurrentProject = doc.Project.Id == GlobalState.CurrentProjectId;
            var projectContext = wasInCurrentProject ? " (Current project - optimized)" : " (Fallback project)";
            Console.Error.WriteLine($"[DEBUG] Document found in workspace: {doc.Name} (Project: {doc.Project.Name}){projectContext}");

            var semanticModel = await doc.GetSemanticModelAsync();
            if (semanticModel == null) return null;

            var syntaxRoot = await doc.GetSyntaxRootAsync();
            if (syntaxRoot == null) return null;

            // Find node at position
            var position = Convert.ToInt32(request.Context?.GetValueOrDefault("position", 0) ?? 0);
            
            // Adjust position check to ensure we are within bounds (snapshot from workspace might be older/newer than file on disk?)
            // Assumption: The file on disk matches what Roslyn loaded. 
            // If the python extractor modified the file, we might need to UpdateText on the document.
            // For now, assume sync worker writes to disk before calling resolve.
            
            if (position >= syntaxRoot.FullSpan.End)
                return new { success = false, error = "Position out of bounds" };

            var token = syntaxRoot.FindToken(position);
            var node = token.Parent;

            if (node == null)
                return new { success = false, error = "No node found at position" };

            var symbolInfo = semanticModel.GetSymbolInfo(node);
            var symbol = symbolInfo.Symbol ?? symbolInfo.CandidateSymbols.FirstOrDefault();

            if (symbol == null)
            {
                return new { success = false, error = "Symbol not resolved" };
            }

            return FormatSymbolResult(symbol);
        }

        static async Task<object> ResolveAdHoc(AnalysisRequest request)
        {
             // Old logic: parse single file string
             var syntaxTree = CSharpSyntaxTree.ParseText(request.Code, path: request.FilePath);
             var compilation = CSharpCompilation.Create(
                 "TempAssembly",
                 new[] { syntaxTree },
                 GetMetadataReferences()
             );

             var semanticModel = compilation.GetSemanticModel(syntaxTree);
             var root = await syntaxTree.GetRootAsync();
             
             var position = Convert.ToInt32(request.Context?.GetValueOrDefault("position", 0) ?? 0);
             var node = root.FindToken(position).Parent;

             if (node == null) 
             {
                 GC.Collect();
                 return new { success = false, error = "No node found at position" };
             }

             var symbolInfo = semanticModel.GetSymbolInfo(node);
             var symbol = symbolInfo.Symbol;

             // Force GC to clear temp compilation and log usage
             GC.Collect();
             if (GlobalState.Workspace != null) Console.Error.WriteLine($"[DEBUG] Fallback to AdHoc Analysis for: {request.FilePath}");

             if (symbol == null) return new { success = false, error = "Symbol not resolved" };

             return FormatSymbolResult(symbol);
        }

        // --- Other Handlers (Refactored to be cleaner) ---

        static async Task<object> AnalyzeFile(AnalysisRequest request)
        {
            // AnalyzeFile remains Ad-Hoc largely because it's extracting local structure. 
            // However, we could use Workspace if available to get better type info.
            // For now, keep as Ad-Hoc to match previous behavior purely.
            
             var syntaxTree = CSharpSyntaxTree.ParseText(request.Code, path: request.FilePath);
             var compilation = CSharpCompilation.Create(
                 "TempAssembly",
                 new[] { syntaxTree },
                 GetMetadataReferences(),
                 new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary)
             );

            var semanticModel = compilation.GetSemanticModel(syntaxTree);
            var root = await syntaxTree.GetRootAsync();

            var symbols = new List<object>();
            
            foreach (var node in root.DescendantNodes())
            {
                ISymbol? symbol = null;
                if (node is ClassDeclarationSyntax c) symbol = semanticModel.GetDeclaredSymbol(c);
                else if (node is InterfaceDeclarationSyntax i) symbol = semanticModel.GetDeclaredSymbol(i);
                else if (node is MethodDeclarationSyntax m) symbol = semanticModel.GetDeclaredSymbol(m);
                else if (node is PropertyDeclarationSyntax p) symbol = semanticModel.GetDeclaredSymbol(p);

                if (symbol != null)
                {
                    symbols.Add(ExtractSymbolInfo(symbol));
                }
            }

            return new
            {
                success = true,
                file_path = request.FilePath,
                symbols = symbols
            };
        }

        static async Task<object> GetInheritanceChain(AnalysisRequest request)
        {
             // Ad-hoc for now
            var syntaxTree = CSharpSyntaxTree.ParseText(request.Code, path: request.FilePath);
            var compilation = CSharpCompilation.Create("TempAssembly", new[] { syntaxTree }, GetMetadataReferences());
            var semanticModel = compilation.GetSemanticModel(syntaxTree);
            var root = await syntaxTree.GetRootAsync();

            var className = request.Context?.GetValueOrDefault("class_name", "")?.ToString() ?? "";
            var classDecl = root.DescendantNodes().OfType<ClassDeclarationSyntax>().FirstOrDefault(c => c.Identifier.Text == className);

            if (classDecl == null) return new { success = false, error = $"Class '{className}' not found" };

            var symbol = semanticModel.GetDeclaredSymbol(classDecl) as INamedTypeSymbol;
            if (symbol == null) return new { success = false, error = "Could not get symbol" };

            var chain = new List<string>();
            var current = symbol.BaseType;
            while (current != null && current.SpecialType != SpecialType.System_Object)
            {
                chain.Add(current.ToDisplayString());
                current = current.BaseType;
            }

            return new
            {
                success = true,
                class_name = className,
                base_classes = chain,
                interfaces = symbol.AllInterfaces.Select(i => i.ToDisplayString()).ToList()
            };
        }

        static async Task<object> AnalyzeEfEntitiesStateless(AnalysisRequest request)
        {
            try
            {
                // Use stateless project loading
                // The request can provide path in ProjectPath (preferred) or FilePath
                var path = !string.IsNullOrEmpty(request.ProjectPath) ? request.ProjectPath : request.FilePath;
                
                if (string.IsNullOrEmpty(path))
                {
                    return new { success = false, error = "project_path required for EF analysis" };
                }

                var project = await GetOrLoadProject(path);
                
                // Get compilation
                var compilation = await project.GetCompilationAsync();
                if (compilation == null)
                {
                    return new { success = false, error = "Failed to get project compilation" };
                }

                // Create analyzer and run analysis
                var analyzer = new EfCoreAnalyzer(project, compilation);
                var result = await analyzer.AnalyzeAllEntitiesAsync(project.FilePath);

                return result;
            }
            catch (Exception ex)
            {
                return new { success = false, error = $"EF analysis failed: {ex.Message}", stack_trace = ex.StackTrace };
            }
        }

        // --- Helpers ---

        static object FormatSymbolResult(ISymbol symbol)
        {
            return new
            {
                success = true,
                symbol = new
                {
                    name = symbol.Name,
                    fully_qualified_name = symbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
                    kind = symbol.Kind.ToString(),
                    containing_type = symbol.ContainingType?.ToDisplayString(),
                    containing_namespace = symbol.ContainingNamespace?.ToDisplayString(),
                    is_external = !symbol.Locations.Any(l => l.IsInSource),
                    assembly_name = symbol.ContainingAssembly?.Name,
                    valid = true,
                    locations = symbol.Locations.Select(loc => new
                    {
                        file_path = loc.SourceTree?.FilePath,
                        line = loc.GetLineSpan().StartLinePosition.Line + 1,
                        column = loc.GetLineSpan().StartLinePosition.Character
                    }).ToList()
                }
            };
        }

        static object ExtractSymbolInfo(ISymbol symbol)
        {
            // Reusing the logic from previous implementation but cleaning it up
            // Use lowercase keys to match Python expectations
            var info = new Dictionary<string, object>
            {
                ["name"] = symbol.Name,
                ["fully_qualified_name"] = symbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
                ["kind"] = symbol.Kind.ToString(),
                ["is_static"] = symbol.IsStatic,
                ["is_abstract"] = symbol.IsAbstract,
                ["is_virtual"] = symbol.IsVirtual,
                ["is_override"] = symbol.IsOverride
            };

            if (symbol is IMethodSymbol m) 
            {
                info["return_type"] = m.ReturnType.ToDisplayString();
                info["parameters"] = m.Parameters.Select(p => new 
                {
                    name = p.Name,
                    type = p.Type.ToDisplayString(),
                    is_optional = p.IsOptional,
                    default_value = p.HasExplicitDefaultValue ? p.ExplicitDefaultValue?.ToString() : null
                }).ToList();
            }
            
            if (symbol is INamedTypeSymbol t)
            {
                info["base_type"] = t.BaseType?.ToDisplayString();
                info["interfaces"] = t.Interfaces.Select(i => i.ToDisplayString()).ToList();
                if (t.IsGenericType)
                {
                    info["generic_parameters"] = t.TypeParameters.Select(tp => new 
                    {
                        name = tp.Name,
                        constraints = tp.ConstraintTypes.Select(c => c.ToDisplayString()).ToList()
                    }).ToList();
                }
            }

            return info;
        }

        static List<MetadataReference> GetMetadataReferences()
        {
            // Basic references for fallback ad-hoc analysis
            var assemblies = new[]
            {
                typeof(object).Assembly,
                typeof(Console).Assembly,
                typeof(Enumerable).Assembly,
            };
            return assemblies.Select(a => MetadataReference.CreateFromFile(a.Location)).Cast<MetadataReference>().ToList();
        }

        static void WriteError(string message)
        {
            Console.WriteLine(JsonConvert.SerializeObject(new { success = false, error = message }, Formatting.None));
        }
    }

    public class AnalysisRequest
    {
        [JsonProperty("operation")] public string Operation { get; set; } = "";
        [JsonProperty("command")] public string Command { set { if(string.IsNullOrEmpty(Operation)) Operation = value; } } // Alias
        [JsonProperty("file_path")] public string FilePath { get; set; } = "";
        [JsonProperty("project_path")] public string? ProjectPath { get; set; }
        [JsonProperty("position")] public int Position { get; set; }
        [JsonProperty("code")] public string Code { get; set; } = "";
        [JsonProperty("context")] public Dictionary<string, object>? Context { get; set; }
    }
}
