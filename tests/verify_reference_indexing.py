import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, Repository, File, Symbol, Relation
from src.parsers.csharp_parser import CSharpParser
from src.extractors.knowledge_extractor import KnowledgeExtractor
from src.config.enums import LanguageEnum, RelationTypeEnum

# Setup in-memory DB
DATABASE_URL = "sqlite+aiosqlite:///:memory:"

async def verify_reference_indexing():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Setup Data
        repo = Repository(name="TestRepo", path="/tmp/test")
        session.add(repo)
        await session.flush()
        
        file_path = "/tmp/test/TestReferences.cs"
        file = File(repository_id=repo.id, path=file_path, name="TestReferences.cs", language=LanguageEnum.CSHARP, size_bytes=100)
        session.add(file)
        await session.flush()
        
        # 2. Create Sample C# Code
        code = """
        using System;
        
        namespace TestNamespace {
            public class User {
                public string Name { get; set; }
            }
            
            public class Service {
                private User _user;
                
                public void Process() {
                    _user = new User();
                    Console.WriteLine(_user.Name);
                    
                    var localName = _user.Name;
                }
            }
        }
        """
        
        # 3. Parse Code
        parser = CSharpParser()
        parse_result = parser.parse(code, file_path)
        
        print(f"Parsed {len(parse_result.symbols)} symbols.")
        for s in parse_result.symbols:
            print(f"Symbol: {s.name}, References: {len(s.references)}")
            for ref in s.references:
                print(f"  - {ref}")

        # 4. Extract Knowledge (runs ReferenceBuilder)
        extractor = KnowledgeExtractor(session)
        result = await extractor.extract_and_persist(parse_result, file.id)
        
        print(f"\nExtraction Result: {result}")
        
        # 5. Verify Relations
        relations = await session.execute(
            "SELECT * FROM relations WHERE relation_type = 'REFERENCES'"
        )
        rows = relations.fetchall()
        print(f"\nFound {len(rows)} REFERENCES relations.")
        
        for row in rows:
            # Fetch from/to symbol names for clarity
            from_sym = await session.get(Symbol, row.from_symbol_id)
            to_sym = await session.get(Symbol, row.to_symbol_id)
            print(f"Relation: {from_sym.name} -> {to_sym.name if to_sym else 'Unknown'} (Metadata: {row.relation_metadata})")

if __name__ == "__main__":
    asyncio.run(verify_reference_indexing())
