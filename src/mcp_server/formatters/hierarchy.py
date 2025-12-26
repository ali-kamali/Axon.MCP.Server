from typing import Dict, Any
from src.utils.layer_detector import LayerDetector

def format_hierarchy_tree(tree: Dict[str, Any], root_name: str, indent: int = 0) -> str:
    """Format call hierarchy tree as text."""
    if not tree or 'symbol' not in tree:
        return ""
    
    lines = []
    symbol = tree['symbol']
    file = tree.get('file')
    prefix = "  " * indent
    
    if indent == 0:
        lines.append(f"{prefix}**{root_name}** ({symbol.kind.value})\\n")
    else:
        lines.append(
            f"{prefix}└─ {symbol.name} ({symbol.kind.value}) - {file.path if file else 'unknown'}:{symbol.start_line}\\n"
        )
    
    for child in tree.get('children', []):
        lines.append(format_hierarchy_tree(child, root_name, indent + 1))
    
    return "".join(lines)


def format_call_chain(chain: Dict, indent: int = 0) -> str:
    """Format call chain as indented tree with layer annotations."""
    formatted = []
    prefix = "  " * indent
    
    # 1. Internal Calls
    if "calls" in chain and chain["calls"]:
        for call in chain["calls"]:
            symbol = call.get("symbol", {})
            layer = symbol.get("layer", "Unknown")
            layer_emoji = LayerDetector.get_layer_emoji(layer)
            
            formatted.append(
                f"{prefix}{layer_emoji} **{symbol.get('name')}** [{layer}] ({symbol.get('kind')})\\n"
                f"{prefix}  {symbol.get('file')}:{symbol.get('line')}\\n"
            )
            formatted.append(format_call_chain(call, indent + 1))

    # 2. Cross-Service API Calls
    if "api_calls" in chain and chain["api_calls"]:
        for call in chain["api_calls"]:
            symbol = call.get("symbol", {})
            layer = symbol.get("layer", "Unknown")
            layer_emoji = LayerDetector.get_layer_emoji(layer)
            
            formatted.append(
                f"{prefix}🌐 **HTTP {call.get('method')} {call.get('url')}**\\n"
                f"{prefix}  ↳ {layer_emoji} **{symbol.get('name')}** [{layer}] in `{symbol.get('repo')}`\\n"
                f"{prefix}  Confidence: {call.get('confidence')}%\\n"
            )
            formatted.append(format_call_chain(call, indent + 1))

    # 3. Published Events
    if "events" in chain and chain["events"]:
        for event in chain["events"]:
            symbol = event.get("symbol", {})
            layer = symbol.get("layer", "Unknown")
            layer_emoji = LayerDetector.get_layer_emoji(layer)
            
            formatted.append(
                f"{prefix}⚡ **Publishes {event.get('event_type')}**\\n"
                f"{prefix}  ↳ Subscribed: {layer_emoji} **{symbol.get('name')}** [{layer}] in `{symbol.get('repo')}`\\n"
                f"{prefix}  Topic: {event.get('topic')}\\n"
            )
            formatted.append(format_call_chain(event, indent + 1))
    
    return "".join(formatted)


def format_module_summary(summary) -> str:
    """Format module summary for display."""
    lines = []

    # Header
    package_indicator = " 📦 Package" if summary.is_package else ""
    lines.append(f"# 🎯 Module Summary: **{summary.module_name}**{package_indicator}\\n")
    lines.append(f"**Path**: `{summary.module_path}`")
    lines.append(f"**Type**: {summary.module_type.replace('_', ' ').title()}")
    lines.append("")

    # Summary
    lines.append("## 📝 Overview\\n")
    lines.append(summary.summary)
    lines.append("")

    # Purpose
    if summary.purpose:
        lines.append("## 🎯 Purpose\\n")
        lines.append(summary.purpose)
        lines.append("")

    # Statistics
    lines.append("## 📊 Statistics\\n")
    lines.append(f"- **Files**: {summary.file_count}")
    lines.append(f"- **Symbols**: {summary.symbol_count}")
    lines.append(f"- **Lines of Code**: {summary.line_count:,}")

    if summary.complexity_score:
        complexity_emoji = "🟢" if summary.complexity_score <= 3 else "🟡" if summary.complexity_score <= 7 else "🔴"
        lines.append(f"- **Complexity**: {complexity_emoji} {summary.complexity_score}/10")
    lines.append("")

    # Entry Points
    if summary.entry_points:
        lines.append("## 🚪 Entry Points\\n")
        for ep in summary.entry_points:
            ep_type = ep.get("type", "unknown").replace("_", " ").title()
            lines.append(f"- `{ep['file']}` ({ep_type})")
        lines.append("")

    # Key Components
    if summary.key_components:
        lines.append("## 🔑 Key Components\\n")
        for comp in summary.key_components[:10]:  # Limit to top 10
            comp_type = comp.get("type", "component").upper()
            lines.append(f"### {comp_type}: `{comp['name']}`")
            if comp.get("description"):
                lines.append(f"{comp['description']}\\n")
        lines.append("")

    # Dependencies
    if summary.dependencies:
        deps = summary.dependencies
        if deps.get("internal") or deps.get("external"):
            lines.append("## 🔗 Dependencies\\n")

            if deps.get("internal"):
                lines.append("**Internal Modules**:")
                for dep in deps["internal"][:5]:
                    lines.append(f"- `{dep}`")
                lines.append("")

            if deps.get("external"):
                lines.append("**External Packages**:")
                for dep in deps["external"][:10]:
                    lines.append(f"- `{dep}`")
                lines.append("")

    # Metadata
    lines.append("---\\n")
    lines.append("## ℹ️ Metadata\\n")
    lines.append(f"- **Generated By**: {summary.generated_by or 'Unknown'}")
    lines.append(f"- **Generated**: {summary.generated_at.strftime('%Y-%m-%d %H:%M:%S') if summary.generated_at else 'Unknown'}")
    lines.append(f"- **Last Updated**: {summary.last_updated.strftime('%Y-%m-%d %H:%M:%S') if summary.last_updated else 'Unknown'}")
    lines.append(f"- **Version**: {summary.version}")
    lines.append("")

    # Tips
    lines.append("## 💡 Next Steps\\n")
    lines.append(f"- Use `get_file_tree(repository_id, path=\\\"{summary.module_path}\\\")` for detailed file structure")
    lines.append(f"- Use `search_by_path(repository_id, path_pattern=\\\"{summary.module_path}/**\\\")` to find specific files")
    lines.append(f"- Use `search_code(query=\\\"...\\\", repository_id)` to find symbols in this module")

    return "\\n".join(lines)
