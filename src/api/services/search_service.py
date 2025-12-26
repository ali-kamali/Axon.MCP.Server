"""Search service for symbol lookup with hybrid search capabilities."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import select, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.search import SearchResult
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.database.models import File, Repository, Symbol, Chunk
from src.embeddings.generator import EmbeddingGenerator
from src.vector_store.pgvector_store import PgVectorStore
from src.utils.logging_config import get_logger
from src.utils.metrics import search_duration, search_queries_total, search_results_count

logger = get_logger(__name__)

# Lazy import Redis cache (optional dependency)
_redis_cache = None


async def _get_redis_cache():
    """Get Redis cache instance (lazy loaded)."""
    global _redis_cache
    if _redis_cache is None:
        try:
            from src.utils.redis_cache import get_cache
            _redis_cache = await get_cache()
        except Exception as e:
            logger.warning("redis_cache_unavailable", error=str(e))
            _redis_cache = False  # Mark as unavailable
    return _redis_cache if _redis_cache else None


class SearchService:
    """Hybrid search service combining keyword and semantic search."""
    
    # Singleton pattern for EmbeddingGenerator to avoid loading model multiple times
    # Note: Not thread-safe, but FastAPI's startup ensures single-threaded initialization
    _embedding_generator: Optional[EmbeddingGenerator] = None
    
    def __init__(self, session: AsyncSession, embedding_generator: Optional[EmbeddingGenerator] = None):
        """
        Initialize search service.
        
        Args:
            session: Database session
            embedding_generator: Optional pre-initialized embedding generator for dependency injection
        """
        self.session = session
        self.vector_store = PgVectorStore(session)
        
        # Use provided generator or shared singleton
        if embedding_generator:
            self.embedding_generator = embedding_generator
        else:
            # Use class-level singleton (lazy-loaded on first use)
            # Note: This is not async-safe for the very first initialization,
            # but in practice FastAPI's startup ensures single-threaded init
            if SearchService._embedding_generator is None:
                logger.info("initializing_shared_embedding_generator")
                SearchService._embedding_generator = EmbeddingGenerator()
            self.embedding_generator = SearchService._embedding_generator
    
    async def search(
        self,
        query: str,
        limit: int = 20,
        repository_id: Optional[int] = None,
        language: Optional[LanguageEnum] = None,
        symbol_kind: Optional[SymbolKindEnum] = None,
        hybrid: bool = True
    ) -> List[SearchResult]:
        """
        Search for code symbols using hybrid approach with caching.
        
        Args:
            query: Search query
            limit: Maximum results
            repository_id: Filter by repository
            language: Filter by language
            symbol_kind: Filter by symbol kind
            hybrid: Use hybrid search (keyword + semantic)
            
        Returns:
            List of search results
            
        Raises:
            ValueError: If parameters are invalid
        """
        # SECURITY: Validate inputs to prevent abuse
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if len(query) > 1000:
            raise ValueError(f"Query too long (max 1000 chars, got {len(query)})")
        
        if limit < 1 or limit > 100:
            raise ValueError(f"Limit must be between 1 and 100, got {limit}")
        
        if repository_id is not None and repository_id < 1:
            raise ValueError(f"Invalid repository_id: {repository_id}")
        
        search_type = "hybrid" if hybrid else "keyword"
        
        # Try to get from cache
        cache = await _get_redis_cache()
        cache_key = None
        
        if cache:
            # Generate cache key from parameters
            cache_key = self._generate_cache_key(query, limit, repository_id, language, symbol_kind, hybrid)
            
            # Try to get cached results
            cached_results = await cache.get(cache_key)
            if cached_results:
                logger.debug("search_cache_hit", query=query, cache_key=cache_key)
                # Convert cached dicts back to SearchResult objects
                # Need to deserialize updated_at from ISO string back to datetime
                for result in cached_results:
                    if result.get('updated_at') and isinstance(result['updated_at'], str):
                        result['updated_at'] = datetime.fromisoformat(result['updated_at'])
                return [SearchResult(**r) for r in cached_results]
        
        # FIXED: Proper error handling with metrics
        try:
            with search_duration.labels(search_type=search_type).time():
                if hybrid:
                    results = await self._hybrid_search(
                        query, limit, repository_id, language, symbol_kind
                    )
                else:
                    results = await self._keyword_search(
                        query, limit, repository_id, language, symbol_kind
                    )
                
                # Cache results if cache is available
                if cache and cache_key:
                    # Convert SearchResult objects to dicts for caching
                    cached_data = [
                        {
                            'symbol_id': r.symbol_id,
                            'file_id': r.file_id,
                            'repository_id': r.repository_id,
                            'repository_name': r.repository_name,
                            'file_path': r.file_path,
                            'language': r.language,
                            'kind': r.kind,
                            'name': r.name,
                            'fully_qualified_name': r.fully_qualified_name,
                            'signature': r.signature,
                            'documentation': r.documentation,
                            'code_snippet': r.code_snippet,
                            'start_line': r.start_line,
                            'end_line': r.end_line,
                            'score': r.score,
                            'match_type': r.match_type,
                            'updated_at': r.updated_at.isoformat() if r.updated_at else None,
                            'context_url': r.context_url
                        }
                        for r in results
                    ]
                    await cache.set(cache_key, cached_data, ttl=300)  # 5 minute TTL
                    logger.debug("search_results_cached", query=query, count=len(results))
                
                search_queries_total.labels(
                    search_type=search_type,
                    status="success"
                ).inc()
                
                search_results_count.labels(search_type=search_type).observe(len(results))
                
                logger.info(
                    "search_completed",
                    query=query,
                    result_count=len(results),
                    hybrid=hybrid
                )
                
                return results
                
        except ValueError as e:
            # Validation errors - don't log as errors, user input issue
            error_msg = f"Failed to search: {str(e)}"
            search_queries_total.labels(
                search_type=search_type,
                status="validation_error"
            ).inc()
            logger.warning("search_validation_failed", query=query, error=error_msg)
            raise
            
        except Exception as e:
            # System errors - log and track
            error_msg = f"Failed to search: {str(e)}"
            search_queries_total.labels(
                search_type=search_type,
                status="error"
            ).inc()
            logger.error(
                "search_failed",
                query=query,
                search_type=search_type,
                error=error_msg,
                exc_info=True
            )
            raise
    
    async def _hybrid_search(
        self,
        query: str,
        limit: int,
        repository_id: Optional[int],
        language: Optional[LanguageEnum],
        symbol_kind: Optional[SymbolKindEnum]
    ) -> List[SearchResult]:
        """Combine keyword and semantic search using reciprocal rank fusion."""
        # Get keyword results
        keyword_results = await self._keyword_search(
            query, limit * 2, repository_id, language, symbol_kind
        )
        
        # Get semantic results
        semantic_results = await self._semantic_search(
            query, limit * 2, repository_id, language, symbol_kind
        )
        
        # Reciprocal rank fusion
        fused_results = self._reciprocal_rank_fusion(
            keyword_results, semantic_results, limit
        )
        
        return fused_results
    
    async def _keyword_search(
        self,
        query: str,
        limit: int,
        repository_id: Optional[int],
        language: Optional[LanguageEnum],
        symbol_kind: Optional[SymbolKindEnum]
    ) -> List[SearchResult]:
        """
        Perform keyword-based search with multi-word tokenization.
        
        ENHANCED: Tokenizes multi-word queries and searches for individual words,
        scoring higher when multiple words match. This makes search more flexible
        and likely to return relevant results.
        """
        query_lower = query.lower()
        
        # Tokenize query into individual words
        # Remove common words and split on whitespace/special chars
        query_tokens = self._tokenize_query(query)
        
        # Build search conditions for both full phrase and individual tokens
        search_conditions = []
        
        # Full phrase match (highest priority)
        search_conditions.append(Symbol.name.ilike(f"%{query}%"))
        search_conditions.append(Symbol.signature.ilike(f"%{query}%"))
        search_conditions.append(Symbol.documentation.ilike(f"%{query}%"))
        search_conditions.append(Symbol.fully_qualified_name.ilike(f"%{query}%"))
        
        # Individual word matches (more flexible)
        for token in query_tokens:
            if len(token) >= 2:  # Skip very short tokens
                search_conditions.append(Symbol.name.ilike(f"%{token}%"))
                search_conditions.append(Symbol.signature.ilike(f"%{token}%"))
                search_conditions.append(Symbol.documentation.ilike(f"%{token}%"))
                search_conditions.append(Symbol.fully_qualified_name.ilike(f"%{token}%"))
        
        # Build base query
        stmt = select(Symbol, File, Repository).join(
            File, Symbol.file_id == File.id
        ).join(
            Repository, File.repository_id == Repository.id
        )
        
        stmt = stmt.where(or_(*search_conditions))
        
        # Apply filters
        if repository_id:
            stmt = stmt.where(Repository.id == repository_id)
        if language:
            stmt = stmt.where(Symbol.language == language)
        if symbol_kind:
            stmt = stmt.where(Symbol.kind == symbol_kind)
        
        # Apply safety limit to prevent memory issues
        SAFETY_LIMIT = 10000
        stmt = stmt.limit(SAFETY_LIMIT)
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        # Get symbol IDs to fetch code snippets
        symbol_ids = [symbol.id for symbol, _, _ in rows]
        code_snippets = await self._get_code_snippets(symbol_ids)
        
        # Convert to SearchResult and calculate multi-word scores
        search_results = []
        for symbol, file, repo in rows:
            # Enhanced scoring with multi-word matching
            score = self._calculate_keyword_score_multiword(symbol, query_lower, query_tokens)
            
            search_results.append(SearchResult(
                symbol_id=symbol.id,
                file_id=file.id,
                repository_id=repo.id,
                name=symbol.name,
                kind=symbol.kind,
                language=symbol.language,
                signature=symbol.signature or "",
                file_path=file.path,
                repository_name=repo.name,
                fully_qualified_name=symbol.fully_qualified_name,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                documentation=symbol.documentation,
                code_snippet=code_snippets.get(symbol.id),  # Add code snippet
                score=score,
                match_type="keyword",
                updated_at=symbol.created_at,
                context_url=f"/api/symbols/{symbol.id}"  # Add context URL
            ))
        
        # Sort by refined score descending, then by name for deterministic ordering
        search_results.sort(key=lambda x: (-x.score, x.name))
        
        # Return top N results after refined scoring
        return search_results[:limit]
    
    async def _semantic_search(
        self,
        query: str,
        limit: int,
        repository_id: Optional[int],
        language: Optional[LanguageEnum],
        symbol_kind: Optional[SymbolKindEnum]
    ) -> List[SearchResult]:
        """Perform semantic search using embeddings."""
        # Generate query embedding
        query_vector = await self.embedding_generator.generate_single_embedding(query)
        
        if not query_vector:
            logger.warning("query_embedding_failed")
            return []
        
        # Build filters
        filters = {}
        if repository_id:
            filters['repository_id'] = repository_id
        if language:
            filters['language'] = language
        if symbol_kind:
            filters['symbol_kind'] = symbol_kind
        
        # Perform vector search with file and repo info in single query
        # This fixes the N+1 query problem
        # ENHANCED: Lowered threshold from 0.7 to 0.5 for more flexible results
        similar_symbols = await self.vector_store.search_similar(
            query_vector=query_vector,
            limit=limit,
            threshold=0.5,  # More permissive threshold
            filters=filters,
            include_file_repo=True  # Fetch File and Repository in one query
        )
        
        # Get code snippets for symbols
        symbol_ids = [symbol.id for symbol, _, _, _ in similar_symbols]
        code_snippets = await self._get_code_snippets(symbol_ids)
        
        # Convert to SearchResult
        search_results = []
        for symbol, similarity, file, repo in similar_symbols:
            if file and repo:  # Should always be present when include_file_repo=True
                search_results.append(SearchResult(
                    symbol_id=symbol.id,
                    file_id=file.id,
                    repository_id=repo.id,
                    name=symbol.name,
                    kind=symbol.kind,
                    language=symbol.language,
                    signature=symbol.signature or "",
                    file_path=file.path,
                    repository_name=repo.name,
                    fully_qualified_name=symbol.fully_qualified_name,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    documentation=symbol.documentation,
                    code_snippet=code_snippets.get(symbol.id),  # Add code snippet
                    score=similarity,
                    match_type="semantic",
                    updated_at=symbol.created_at,
                    context_url=f"/api/symbols/{symbol.id}"  # Add context URL
                ))
        
        return search_results
    
    def _generate_cache_key(
        self,
        query: str,
        limit: int,
        repository_id: Optional[int],
        language: Optional[LanguageEnum],
        symbol_kind: Optional[SymbolKindEnum],
        hybrid: bool
    ) -> str:
        """Generate cache key from search parameters."""
        # Create deterministic key
        key_parts = [
            "search",
            query,
            str(limit),
            str(repository_id) if repository_id else "all",
            language.value if language else "all",
            symbol_kind.value if symbol_kind else "all",
            "hybrid" if hybrid else "keyword"
        ]
        
        key_str = ":".join(key_parts)
        
        # Hash if too long
        if len(key_str) > 200:
            key_hash = hashlib.md5(key_str.encode()).hexdigest()
            return f"search:{key_hash}"
        
        return key_str
    
    async def _get_code_snippets(self, symbol_ids: List[int], max_length: int = 2000) -> Dict[int, str]:
        """
        Get code snippets for symbols from their chunks.
        
        Args:
            symbol_ids: List of symbol IDs
            max_length: Maximum snippet length
            
        Returns:
            Dict mapping symbol_id to code snippet
        """
        if not symbol_ids:
            return {}
        
        try:
            # Get chunks for these symbols (limit to first chunk per symbol for preview)
            stmt = (
                select(Chunk.symbol_id, Chunk.content)
                .where(Chunk.symbol_id.in_(symbol_ids))
                .order_by(Chunk.symbol_id, Chunk.id)
            )
            
            result = await self.session.execute(stmt)
            rows = result.all()
            
            # Build snippets dict (first chunk per symbol)
            snippets = {}
            for symbol_id, content in rows:
                if symbol_id not in snippets and content:
                    # Truncate long content
                    if len(content) > max_length:
                        snippet = content[:max_length] + "..."
                    else:
                        snippet = content
                    snippets[symbol_id] = snippet
            
            return snippets
            
        except Exception as e:
            logger.warning("failed_to_fetch_code_snippets", error=str(e))
            return {}
    
    def _tokenize_query(self, query: str) -> List[str]:
        """
        Tokenize query into individual words, filtering out common stop words.
        
        Args:
            query: Search query string
            
        Returns:
            List of query tokens
        """
        # Common stop words to ignore (keep it minimal for code search)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # Split on whitespace and special characters, keep alphanumeric
        tokens = re.findall(r'\w+', query.lower())
        
        # Filter out stop words and very short tokens
        tokens = [t for t in tokens if t not in stop_words and len(t) >= 2]
        
        return tokens
    
    def _calculate_keyword_score(self, symbol: Symbol, query: str) -> float:
        """Calculate keyword relevance score (legacy single-phrase scoring)."""
        score = 0.0
        
        # Exact name match is highest priority
        if symbol.name.lower() == query:
            score += 1.0
        elif query in symbol.name.lower():
            score += 0.7
        
        # Signature match
        if symbol.signature and query in symbol.signature.lower():
            score += 0.3
        
        # Documentation match
        if symbol.documentation and query in symbol.documentation.lower():
            score += 0.2
        
        return score
    
    def _calculate_keyword_score_multiword(self, symbol: Symbol, query: str, tokens: List[str]) -> float:
        """
        Calculate keyword relevance score with multi-word token matching.
        
        Args:
            symbol: Symbol to score
            query: Original full query
            tokens: Individual query tokens
            
        Returns:
            Relevance score (higher is better)
        """
        score = 0.0
        symbol_name_lower = symbol.name.lower()
        symbol_sig_lower = (symbol.signature or "").lower()
        symbol_doc_lower = (symbol.documentation or "").lower()
        symbol_fqn_lower = (symbol.fully_qualified_name or "").lower()
        
        # 1. Exact full phrase match (highest priority)
        if symbol_name_lower == query:
            score += 10.0
        elif query in symbol_name_lower:
            score += 5.0
        elif query in symbol_fqn_lower:
            score += 4.0
        elif query in symbol_sig_lower:
            score += 2.0
        elif query in symbol_doc_lower:
            score += 1.0
        
        # 2. Multi-word token matching (flexible matching)
        if tokens:
            matched_tokens = 0
            for token in tokens:
                token_found = False
                
                # Check name
                if token in symbol_name_lower:
                    score += 2.0
                    token_found = True
                
                # Check fully qualified name
                if token in symbol_fqn_lower:
                    score += 1.5
                    token_found = True
                
                # Check signature
                if token in symbol_sig_lower:
                    score += 1.0
                    token_found = True
                
                # Check documentation
                if token in symbol_doc_lower:
                    score += 0.5
                    token_found = True
                
                if token_found:
                    matched_tokens += 1
            
            # Bonus for matching multiple tokens (indicates better relevance)
            if len(tokens) > 1:
                match_ratio = matched_tokens / len(tokens)
                score += match_ratio * 3.0  # Up to 3 bonus points
        
        return score
    
    def _reciprocal_rank_fusion(
        self,
        keyword_results: List[SearchResult],
        semantic_results: List[SearchResult],
        limit: int,
        k: int = 60
    ) -> List[SearchResult]:
        """
        Combine results using reciprocal rank fusion.
        
        Args:
            keyword_results: Results from keyword search
            semantic_results: Results from semantic search
            limit: Number of results to return
            k: RRF constant (typically 60)
            
        Returns:
            Fused results
        """
        # Build fusion scores
        fusion_scores: Dict[int, float] = {}
        result_map: Dict[int, SearchResult] = {}
        
        # Add keyword results
        for rank, result in enumerate(keyword_results, 1):
            fusion_scores[result.symbol_id] = fusion_scores.get(result.symbol_id, 0) + (1 / (k + rank))
            result_map[result.symbol_id] = result
        
        # Add semantic results
        for rank, result in enumerate(semantic_results, 1):
            fusion_scores[result.symbol_id] = fusion_scores.get(result.symbol_id, 0) + (1 / (k + rank))
            result_map[result.symbol_id] = result
        
        # Sort by fusion score
        sorted_ids = sorted(fusion_scores.keys(), key=lambda x: fusion_scores[x], reverse=True)
        
        # Return top results
        results = []
        for symbol_id in sorted_ids[:limit]:
            result = result_map[symbol_id]
            result.score = fusion_scores[symbol_id]
            result.match_type = "hybrid"
            results.append(result)
        
        return results
