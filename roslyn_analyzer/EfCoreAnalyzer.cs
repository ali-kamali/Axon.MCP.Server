using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Newtonsoft.Json;

namespace RoslynAnalyzer
{
    /// <summary>
    /// Analyzes Entity Framework Core entity mappings using Roslyn static analysis.
    /// Extracts table names, column mappings, primary keys, relationships from Data Annotations and Fluent API.
    /// </summary>
    public class EfCoreAnalyzer
    {
        private readonly Project _project;
        private readonly Compilation _compilation;

        public EfCoreAnalyzer(Project project, Compilation compilation)
        {
            _project = project;
            _compilation = compilation;
        }

        /// <summary>
        /// Analyze all EF Core entities in the project.
        /// </summary>
        public async Task<object> AnalyzeAllEntitiesAsync(string projectPath)
        {
            try
            {
                var entities = new List<object>();
                var dbContexts = await FindDbContextClassesAsync();

                // Find all potential entity classes
                var entityClasses = await FindPotentialEntityClassesAsync();

                foreach (var entityClass in entityClasses)
                {
                    var entityMapping = await AnalyzeEntityAsync(entityClass, dbContexts);
                    if (entityMapping != null)
                    {
                        entities.Add(entityMapping);
                    }
                }

                return new
                {
                    success = true,
                    project_path = projectPath,
                    entity_count = entities.Count,
                    entities = entities
                };
            }
            catch (Exception ex)
            {
                return new
                {
                   success = false,
                    error = $"Failed to analyze entities: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Analyze a single entity class.
        /// </summary>
        private async Task<object> AnalyzeEntityAsync(INamedTypeSymbol entityClass, List<DbContextInfo> dbContexts)
        {
            try
            {
                var entityName = entityClass.Name;
                var namespaceName = entityClass.ContainingNamespace?.ToDisplayString();

                // Extract Data Annotations
                var tableName = entityName; // Default convention
                string schemaName = null;
                var primaryKeys = new List<string>();
                var properties = new List<object>();

                // Check for [Table] attribute
                var tableAttr = entityClass.GetAttributes().FirstOrDefault(a => a.AttributeClass?.Name == "TableAttribute");
                if (tableAttr != null)
                {
                    if (tableAttr.ConstructorArguments.Length > 0)
                    {
                        tableName = tableAttr.ConstructorArguments[0].Value?.ToString();
                    }
// Check for Schema named argument
                    var schemaArg = tableAttr.NamedArguments.FirstOrDefault(na => na.Key == "Schema");
                    if (schemaArg.Value.Value != null)
                    {
                        schemaName = schemaArg.Value.Value.ToString();
                    }
                }

                // Analyze properties
                foreach (var property in entityClass.GetMembers().OfType<IPropertySymbol>())
                {
                    if (property.IsStatic || property.DeclaredAccessibility != Accessibility.Public)
                        continue;

                    var propertyInfo = AnalyzeProperty(property, ref primaryKeys);
                    if (propertyInfo != null)
                    {
                        properties.Add(propertyInfo);
                    }
                }

                // Apply Fluent API overrides
                var fluentConfig = FindFluentApiConfiguration(entityClass, dbContexts);
                if (fluentConfig != null)
                {
                    ApplyFluentApiOverrides(ref tableName, ref schemaName, ref primaryKeys, properties, fluentConfig);
                }

                // If no primary key found, use "Id" convention
                if (primaryKeys.Count == 0)
                {
                    var idProperty = properties.Cast<dynamic>().FirstOrDefault(p => p.name == "Id");
                    if (idProperty != null)
                    {
                        primaryKeys.Add("Id");
                    }
                }

                return new
                {
                    entity = entityName,
                    @namespace = namespaceName,
                    table_name = tableName,
                    schema_name = schemaName,
                    primary_keys = primaryKeys.ToArray(),
                    properties = properties,
                    relationships = ExtractRelationships(entityClass, dbContexts),
                    raw_mapping = new
                    {
                        has_fluent_config = fluentConfig != null,
                        class_attributes = entityClass.GetAttributes().Select(a => a.AttributeClass?.Name).ToList()
                    }
                };
            }
            catch (Exception ex)
            {
                return null; // Skip entities that fail to analyze
            }
        }

        /// <summary>
        /// Analyze a single property for column mapping.
        /// </summary>
        private object AnalyzeProperty(IPropertySymbol property, ref List<string> primaryKeys)
        {
            var propertyName = property.Name;
            var columnName = propertyName; // Default convention
            var propertyType = property.Type.ToDisplayString();
            var isNullable = property.Type.NullableAnnotation == NullableAnnotation.Annotated;
            var isPrimaryKey = false;
            var isForeignKey = false;
            string foreignKeyTo = null;
            var constraints = new List<string>();

            // Check for [Key] attribute
            var keyAttr = property.GetAttributes().FirstOrDefault(a => a.AttributeClass?.Name == "KeyAttribute");
            if (keyAttr != null)
            {
                isPrimaryKey = true;
                primaryKeys.Add(propertyName);
            }

            // Check for [Column] attribute
            var columnAttr = property.GetAttributes().FirstOrDefault(a => a.AttributeClass?.Name == "ColumnAttribute");
            if (columnAttr != null)
            {
                if (columnAttr.ConstructorArguments.Length > 0)
                {
                    columnName = columnAttr.ConstructorArguments[0].Value?.ToString();
                }

                // Check for TypeName named argument (e.g., "varchar(100)")
                var typeNameArg = columnAttr.NamedArguments.FirstOrDefault(na => na.Key == "TypeName");
                if (typeNameArg.Value.Value != null)
                {
                    constraints.Add(typeNameArg.Value.Value.ToString());
                }
            }

            // Check for [Required] attribute
            var requiredAttr = property.GetAttributes().FirstOrDefault(a => a.AttributeClass?.Name == "RequiredAttribute");
            if (requiredAttr != null)
            {
                isNullable = false;
            }

            // Check for [MaxLength] or [StringLength] attribute
            var maxLengthAttr = property.GetAttributes().FirstOrDefault(a => 
                a.AttributeClass?.Name == "MaxLengthAttribute" || a.AttributeClass?.Name == "StringLengthAttribute");
            if (maxLengthAttr != null && maxLengthAttr.ConstructorArguments.Length > 0)
            {
                var maxLengthValue = maxLengthAttr.ConstructorArguments[0].Value;
                constraints.Add($"maxlength({maxLengthValue})");
            }

            // Check for [ForeignKey] attribute
            var foreignKeyAttr = property.GetAttributes().FirstOrDefault(a => a.AttributeClass?.Name == "ForeignKeyAttribute");
            if (foreignKeyAttr != null)
            {
                isForeignKey = true;
                if (foreignKeyAttr.ConstructorArguments.Length > 0)
                {
                    foreignKeyTo = foreignKeyAttr.ConstructorArguments[0].Value?.ToString();
                }
            }

            // Skip navigation properties (collections or reference types that aren't value types)
            if (property.Type is INamedTypeSymbol namedType)
            {
                // Skip ICollection<T>, IEnumerable<T>, List<T>, etc.
                if (namedType.IsGenericType)
                {
                    var genericDef = namedType.OriginalDefinition.ToDisplayString();
                    if (genericDef.Contains("ICollection") || genericDef.Contains("IEnumerable") || 
                        genericDef.Contains("List") || genericDef.Contains("HashSet"))
                    {
                        return null; // Skip collections - these are navigation properties
                    }
                }

                // Skip reference navigation properties (non-primitive types without [Column])
                if (!IsPrimitiveType(propertyType) && columnAttr == null && !isPrimaryKey && !isForeignKey)
                {
                    return null; // Likely a navigation property
                }
            }

            return new
            {
                name = propertyName,
                column = columnName,
                type = SimplifyTypeName(propertyType),
                is_nullable = isNullable,
                is_primary_key = isPrimaryKey,
                is_foreign_key = isForeignKey,
                foreign_key_to = foreignKeyTo,
                constraints = constraints.ToArray()
            };
        }

        /// <summary>
        /// Find all DbContext classes in the compilation.
        /// </summary>
        private async Task<List<DbContextInfo>> FindDbContextClassesAsync()
        {
            var dbContexts = new List<DbContextInfo>();

            foreach (var document in _project.Documents)
            {
                var syntaxTree = await document.GetSyntaxTreeAsync();
                if (syntaxTree == null) continue;

                var semanticModel = await document.GetSemanticModelAsync();
                if (semanticModel == null) continue;

                var root = await syntaxTree.GetRootAsync();
                var classes = root.DescendantNodes().OfType<ClassDeclarationSyntax>();

                foreach (var classDecl in classes)
                {
                    var classSymbol = semanticModel.GetDeclaredSymbol(classDecl) as INamedTypeSymbol;
                    if (classSymbol == null) continue;

                    // Check if inherits from DbContext
                    if (InheritsFromDbContext(classSymbol))
                    {
                        var onModelCreatingMethod = classDecl.Members
                            .OfType<MethodDeclarationSyntax>()
                            .FirstOrDefault(m => m.Identifier.Text == "OnModelCreating");

                        dbContexts.Add(new DbContextInfo
                        {
                            ClassName = classSymbol.Name,
                            ClassSymbol = classSymbol,
                            OnModelCreating = onModelCreatingMethod,
                            SemanticModel = semanticModel
                        });
                    }
                }
            }

            return dbContexts;
        }

        /// <summary>
        /// Find all potential entity classes (POCOs with public properties).
        /// </summary>
        private async Task<List<INamedTypeSymbol>> FindPotentialEntityClassesAsync()
        {
            var entities = new List<INamedTypeSymbol>();

            foreach (var document in _project.Documents)
            {
                var semanticModel = await document.GetSemanticModelAsync();
                if (semanticModel == null) continue;

                var root = await document.GetSyntaxRootAsync();
                if (root == null) continue;

                var classes = root.DescendantNodes().OfType<ClassDeclarationSyntax>();

                foreach (var classDecl in classes)
                {
                    var classSymbol = semanticModel.GetDeclaredSymbol(classDecl) as INamedTypeSymbol;
                    if (classSymbol == null || classSymbol.IsAbstract || classSymbol.IsStatic)
                        continue;

                    // Heuristic: class with public properties, not a DbContext
                    if (!InheritsFromDbContext(classSymbol) && HasPublicProperties(classSymbol))
                    {
                        entities.Add(classSymbol);
                    }
                }
            }

            return entities;
        }

        /// <summary>
        /// Find Fluent API configuration for an entity in DbContext.OnModelCreating.
        /// </summary>
        private FluentApiConfig FindFluentApiConfiguration(INamedTypeSymbol entityClass, List<DbContextInfo> dbContexts)
        {
            // Implementation would parse OnModelCreating method body
            // Looking for modelBuilder.Entity<EntityName>() calls
            // This is complex and would require analyzing lambda expressions
            // For now, return null (will be implemented in next iteration)
            return null;
        }

        /// <summary>
        /// Apply Fluent API overrides to entity mapping.
        /// </summary>
        private void ApplyFluentApiOverrides(ref string tableName, ref string schemaName, 
            ref List<string> primaryKeys, List<object> properties, FluentApiConfig fluentConfig)
        {
            // Apply overrides from Fluent API configuration
            // Implementation details depend on FluentApiConfig structure
        }

        /// <summary>
        /// Extract navigation properties and relationships.
        /// </summary>
        private List<object> ExtractRelationships(INamedTypeSymbol entityClass, List<DbContextInfo> dbContexts)
        {
            var relationships = new List<object>();

            foreach (var property in entityClass.GetMembers().OfType<IPropertySymbol>())
            {
                if (property.IsStatic || property.DeclaredAccessibility != Accessibility.Public)
                    continue;

                var propertyType = property.Type;

                // Check for collection navigation properties (one-to-many)
                if (propertyType is INamedTypeSymbol namedType && namedType.IsGenericType)
                {
                    var genericDef = namedType.OriginalDefinition.ToDisplayString();
                    if (genericDef.Contains("ICollection") || genericDef.Contains("List") || 
                        genericDef.Contains("IEnumerable") || genericDef.Contains("HashSet"))
                    {
                        var targetEntity = namedType.TypeArguments.FirstOrDefault()?.Name;
                        if (targetEntity != null)
                        {
                            relationships.Add(new
                            {
                                navigation_property = property.Name,
                                relationship_type = "one-to-many",
                                target_entity = targetEntity
                            });
                        }
                    }
                }
                // Check for reference navigation properties (many-to-one or one-to-one)
                else if (propertyType is INamedTypeSymbol refType && !IsPrimitiveType(refType.ToDisplayString()))
                {
                    // Check if there's a corresponding foreign key property
                    var foreignKeyProperty = entityClass.GetMembers().OfType<IPropertySymbol>()
                        .FirstOrDefault(p => p.Name == $"{property.Name}Id");

                    if (foreignKeyProperty != null)
                    {
                        relationships.Add(new
                        {
                            navigation_property = property.Name,
                            relationship_type = "many-to-one",
                            target_entity = refType.Name,
                            foreign_key = foreignKeyProperty.Name,
                            principal_key = "Id" // Convention
                        });
                    }
                }
            }

            return relationships;
        }

        // Helper methods

        private bool InheritsFromDbContext(INamedTypeSymbol classSymbol)
        {
            var baseType = classSymbol.BaseType;
            while (baseType != null)
            {
                if (baseType.Name == "DbContext")
                    return true;
                baseType = baseType.BaseType;
            }
            return false;
        }

        private bool HasPublicProperties(INamedTypeSymbol classSymbol)
        {
            return classSymbol.GetMembers().OfType<IPropertySymbol>()
                .Any(p => p.DeclaredAccessibility == Accessibility.Public && !p.IsStatic);
        }

        private bool IsPrimitiveType(string typeName)
        {
            var primitives = new HashSet<string>
            {
                "int", "long", "short", "byte", "sbyte", "uint", "ulong", "ushort",
                "float", "double", "decimal", "bool", "char", "string",
                "DateTime", "DateTimeOffset", "TimeSpan", "Guid",
                "System.Int32", "System.Int64", "System.String", "System.DateTime", "System.Guid"
            };

            return primitives.Contains(typeName) || primitives.Contains(typeName.Replace("?", ""));
        }

        private string SimplifyTypeName(string typeName)
        {
            // Remove System. prefix and nullable markers for cleaner output
            return typeName
                .Replace("System.", "")
                .Replace("?", "")
                .Replace("[]", "");
        }

        // Helper classes

        private class DbContextInfo
        {
            public string ClassName { get; set; }
            public INamedTypeSymbol ClassSymbol { get; set; }
            public MethodDeclarationSyntax OnModelCreating { get; set; }
            public SemanticModel SemanticModel { get; set; }
        }

        private class FluentApiConfig
        {
            public string TableName { get; set; }
            public string SchemaName { get; set; }
            public List<string> PrimaryKeys { get; set; }
            public Dictionary<string, string> ColumnMappings { get; set; }
        }
    }
}
