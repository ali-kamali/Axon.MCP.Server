from typing import Dict, List

def format_repository_list(repos: List[Dict]) -> str:
    """Format repository list for ChatGPT display."""
    if not repos:
        return "No repositories available."

    formatted = [f"Available repositories ({len(repos)}):\n\n"]

    for repo in repos:
        # Format size
        size_mb = repo['size_bytes'] / (1024 * 1024) if repo['size_bytes'] > 0 else 0
        
        formatted.append(
            f"**{repo['name']}** ({repo['provider']})\n"
            f"  📦 Path: {repo['path_with_namespace']}\n"
            f"  🌿 Branch: {repo['default_branch']}\n"
            f"  📊 Status: {repo['status']}\n"
            f"  📄 Files: {repo['total_files']:,} | Symbols: {repo['total_symbols']:,} | Size: {size_mb:.1f} MB\n"
            f"  🔄 Last synced: {repo['last_synced'] or 'Never'}\n"
            f"  🔗 Repository ID: {repo['id']}\n"
            f"  🌐 URL: {repo['url']}\n"
            f"  💡 Use search_code(repository_name='{repo['name']}') to search this repo\n"
            f"  💡 Use get_file_content(repository_id={repo['id']}, file_path='...') to read files\n"
            f"\n"
        )

    return "".join(formatted)
