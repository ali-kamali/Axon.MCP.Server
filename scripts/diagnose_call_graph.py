"""Diagnose why call graph has 0 relationships."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.session import AsyncSessionLocal
from sqlalchemy import select, func, text
from src.database.models import Symbol, File
from src.config.enums import SymbolKindEnum, LanguageEnum


async def diagnose():
    """Run diagnostic queries to find the issue."""
    
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("CALL GRAPH DIAGNOSTIC REPORT")
        print("=" * 80)
        
        # 1. Check parent_name vs class FQN matching
        print("\n1. Checking if method parent_names match class fully_qualified_names...")
        
        query = text("""
            SELECT 
                COUNT(DISTINCT m.parent_name) as unique_parent_names,
                COUNT(DISTINCT CASE WHEN c.id IS NOT NULL THEN m.parent_name END) as matching_parents,
                COUNT(DISTINCT CASE WHEN c.id IS NULL THEN m.parent_name END) as orphan_parents
            FROM symbols m
            LEFT JOIN symbols c ON m.parent_name = c.fully_qualified_name 
                AND c.kind IN ('CLASS', 'INTERFACE')
            WHERE m.kind = 'METHOD' 
              AND m.language = 'CSHARP'
        """)
        
        result = await session.execute(query)
        row = result.first()
        
        print(f"   Unique parent names: {row[0]}")
        print(f"   Matching parent classes: {row[1]}")
        print(f"   Orphan parents (no matching class): {row[2]}")
        
        if row[2] > 0:
            print(f"\n   ⚠️  ISSUE FOUND: {row[2]} parent names don't match any class!")
            print("   This means methods can't find their parent classes.")
        
        # 2. Show sample mismatches
        print("\n2. Sample method parent_names vs class fully_qualified_names:")
        
        query = text("""
            SELECT 
                m.name as method_name,
                m.parent_name,
                c.fully_qualified_name as class_fqn,
                CASE WHEN c.id IS NULL THEN 'NOT FOUND' ELSE 'FOUND' END as class_exists
            FROM symbols m
            LEFT JOIN symbols c ON m.parent_name = c.fully_qualified_name 
                AND c.kind IN ('CLASS', 'INTERFACE')
            WHERE m.kind = 'METHOD' 
              AND m.language = 'CSHARP'
            LIMIT 10
        """)
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        for row in rows:
            status = "✅" if row[3] == "FOUND" else "❌"
            print(f"   {status} Method: {row[0]}")
            print(f"      Parent name: {row[1]}")
            print(f"      Class FQN: {row[2] or 'NOT FOUND'}")
            print()
        
        # 3. Check if it's a namespace issue
        print("\n3. Checking for namespace mismatches...")
        
        query = text("""
            SELECT 
                m.parent_name,
                c.name as class_name,
                c.fully_qualified_name as class_fqn,
                COUNT(*) as method_count
            FROM symbols m
            LEFT JOIN symbols c ON c.name = SPLIT_PART(m.parent_name, '.', -1)
                AND c.kind IN ('CLASS', 'INTERFACE')
                AND c.language = 'CSHARP'
            WHERE m.kind = 'METHOD' 
              AND m.language = 'CSHARP'
            GROUP BY m.parent_name, c.name, c.fully_qualified_name
            LIMIT 10
        """)
        
        try:
            result = await session.execute(query)
            rows = result.fetchall()
            
            print("   Sample parent_name to class_name mappings:")
            for row in rows:
                print(f"   Method parent: {row[0]}")
                print(f"   Class name: {row[1] or 'NOT FOUND'}")
                print(f"   Class FQN: {row[2] or 'NOT FOUND'}")
                print(f"   Methods: {row[3]}")
                print()
        except Exception as e:
            print(f"   Note: SPLIT_PART not available, trying alternative...")
            
            # Alternative without SPLIT_PART
            query = text("""
                SELECT 
                    m.parent_name,
                    c.name as class_name,
                    c.fully_qualified_name as class_fqn,
                    COUNT(*) as method_count
                FROM symbols m
                LEFT JOIN symbols c ON m.parent_name LIKE '%' || c.name
                    AND c.kind IN ('CLASS', 'INTERFACE')
                    AND c.language = 'CSHARP'
                WHERE m.kind = 'METHOD' 
                  AND m.language = 'CSHARP'
                GROUP BY m.parent_name, c.name, c.fully_qualified_name
                LIMIT 10
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            for row in rows:
                print(f"   Method parent: {row[0]}")
                print(f"   Class name: {row[1] or 'NOT FOUND'}")
                print(f"   Class FQN: {row[2] or 'NOT FOUND'}")
                print(f"   Methods: {row[3]}")
                print()
        
        # 4. Show actual examples
        print("\n4. Actual examples from database:")
        
        result = await session.execute(
            select(Symbol)
            .where(
                Symbol.kind == SymbolKindEnum.METHOD,
                Symbol.language == LanguageEnum.CSHARP
            )
            .limit(3)
        )
        
        methods = result.scalars().all()
        
        for method in methods:
            print(f"\n   Method: {method.name}")
            print(f"   Parent name: {method.parent_name}")
            print(f"   FQN: {method.fully_qualified_name}")
            
            # Try to find parent class
            parent_result = await session.execute(
                select(Symbol)
                .where(
                    Symbol.fully_qualified_name == method.parent_name,
                    Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE])
                )
            )
            parent = parent_result.scalar_one_or_none()
            
            if parent:
                print(f"   ✅ Parent class FOUND: {parent.name}")
            else:
                print(f"   ❌ Parent class NOT FOUND for: {method.parent_name}")
                
                # Try fuzzy match
                fuzzy_result = await session.execute(
                    select(Symbol)
                    .where(
                        Symbol.name == method.parent_name.split('.')[-1] if '.' in method.parent_name else method.parent_name,
                        Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE])
                    )
                    .limit(1)
                )
                fuzzy_parent = fuzzy_result.scalar_one_or_none()
                
                if fuzzy_parent:
                    print(f"   💡 FOUND by name match: {fuzzy_parent.fully_qualified_name}")
                    print(f"   🔧 FIX: parent_name should be '{fuzzy_parent.fully_qualified_name}' not '{method.parent_name}'")
        
        print("\n" + "=" * 80)
        print("DIAGNOSIS COMPLETE")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(diagnose())
