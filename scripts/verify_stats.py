import asyncio
import httpx
import sys

async def verify_statistics():
    base_url = "http://localhost:8001/api/v1"
    
    async with httpx.AsyncClient() as client:
        # 1. Check Overview
        print("Checking Overview Statistics...")
        try:
            response = await client.get(f"{base_url}/statistics/overview")
            response.raise_for_status()
            overview = response.json()
            print("Overview Stats:")
            print(f"  Repositories: {overview['total_repositories']}")
            print(f"  Files: {overview['total_files']}")
            print(f"  Symbols: {overview['total_symbols']}")
            print(f"  Endpoints: {overview['total_endpoints']}")
            print(f"  Top Languages: {len(overview['top_languages'])}")
        except Exception as e:
            print(f"Failed to get overview: {e}")
            return

        # 2. Check Repository Stats (if any repos exist)
        if overview['total_repositories'] > 0:
            # Get a repository ID
            repos_resp = await client.get(f"{base_url}/repositories?limit=1")
            repos = repos_resp.json()['items']
            if repos:
                repo_id = repos[0]['id']
                print(f"\nChecking Statistics for Repository {repo_id}...")
                try:
                    response = await client.get(f"{base_url}/statistics/repository/{repo_id}")
                    response.raise_for_status()
                    repo_stats = response.json()
                    print("Repository Stats:")
                    print(f"  Name: {repo_stats['repository_name']}")
                    print(f"  Files: {repo_stats['total_files']}")
                    print(f"  Symbols: {repo_stats['total_symbols']}")
                    print(f"  Endpoints: {repo_stats['total_endpoints']}")
                    print(f"  Empty Files: {repo_stats['files_with_no_symbols']}")
                    print(f"  Avg Symbols/File: {repo_stats['avg_symbols_per_file']}")
                    
                    print("\n  Symbol Distribution:")
                    for item in repo_stats['symbol_distribution']:
                        print(f"    {item['kind']}: {item['count']}")
                        
                    print("\n  Relationship Distribution:")
                    for item in repo_stats['relationship_distribution']:
                        print(f"    {item['relation_type']}: {item['count']}")
                        
                except Exception as e:
                    print(f"Failed to get repository stats: {e}")
        else:
            print("\nNo repositories found to verify per-repository stats.")

if __name__ == "__main__":
    asyncio.run(verify_statistics())
