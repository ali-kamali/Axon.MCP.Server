import asyncio
import sys
import os
from dotenv import load_dotenv
from sqlalchemy import select, func, and_

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables
load_dotenv()

# FORCE LOCALHOST for testing if needed
db_url = os.getenv("DATABASE_URL", "")
if db_url and "@db:" in db_url:
    print("DEBUG: Replacing 'db' host with 'localhost'")
    os.environ["DATABASE_URL"] = db_url.replace("@db:", "@localhost:")
elif db_url and "@postgres:" in db_url:
    print("DEBUG: Replacing 'postgres' host with 'localhost'")
    os.environ["DATABASE_URL"] = db_url.replace("@postgres:", "@localhost:")

from src.database.session import get_async_session
from src.database.models import Relation, Symbol, Repository, File
from src.config.enums import RelationTypeEnum, SymbolKindEnum
from src.utils.call_graph_traversal import CallGraphTraverser, TraversalConfig, TraversalDirection

async def verify_call_graph():
    print("Verifying Call Graph Data & Traversal...")
    
    async with get_async_session() as session:
        # 1. Check total relationships
        result = await session.execute(select(func.count(Relation.id)))
        total_relations = result.scalar()
        print(f"\nTotal Relationships: {total_relations}")
        
        # 2. Check CALLS relationships
        result = await session.execute(
            select(func.count(Relation.id))
            .where(Relation.relation_type == RelationTypeEnum.CALLS)
        )
        calls_relations = result.scalar()
        print(f"CALLS Relationships: {calls_relations}")
        
        # 3. Check distribution by repository
        print("\nRelationships by Repository:")
        result = await session.execute(
            select(Repository.name, func.count(Relation.id))
            .join(File, Repository.id == File.repository_id)
            .join(Symbol, File.id == Symbol.file_id)
            .join(Relation, Symbol.id == Relation.from_symbol_id)
            .group_by(Repository.name)
        )
        for repo_name, count in result.all():
            print(f"  - {repo_name}: {count}")
            
        # 4. Find a symbol with CALLS relationships to test traversal
        print("\nFinding a suitable test symbol...")
        subquery = (
            select(Relation.from_symbol_id)
            .where(Relation.relation_type == RelationTypeEnum.CALLS)
            .group_by(Relation.from_symbol_id)
            .having(func.count(Relation.id) > 0)
            .limit(1)
        )
        
        result = await session.execute(
            select(Symbol, File, Repository)
            .join(File, Symbol.file_id == File.id)
            .join(Repository, File.repository_id == Repository.id)
            .where(Symbol.id.in_(subquery))
        )
        row = result.first()
        
        if not row:
            print("No symbols found with CALLS relationships! Cannot test traversal.")
            return
            
        symbol, file, repo = row
        print(f"Found test symbol: {symbol.name} (ID: {symbol.id})")
        print(f"   File: {file.path}")
        print(f"   Repo: {repo.name}")
        
        # 5. Test Traversal
        print(f"\nTesting Traversal (Depth=3)...")
        traverser = CallGraphTraverser(session)
        config = TraversalConfig(
            depth=3,
            direction=TraversalDirection.DOWNSTREAM,
            relation_types=[RelationTypeEnum.CALLS]
        )
        
        result = await traverser.traverse(symbol.id, config)
        
        if result:
            print(f"   Total Symbols Found: {result.total_symbols}")
            print(f"   Max Depth Reached: {result.max_depth_reached}")
            print(f"   Cycles Detected: {result.cycles_detected}")
            
            print("\n   Related Symbols:")
            for node in result.related_symbols:
                print(f"   - [Depth {node.depth}] {node.name} ({node.kind})")
        else:
            print("Traversal returned None")

if __name__ == "__main__":
    asyncio.run(verify_call_graph())
