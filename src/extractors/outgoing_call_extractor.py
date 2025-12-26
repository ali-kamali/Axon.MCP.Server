"""
Extractor for outgoing API calls (HTTP) from code.
"""

from typing import List, Dict, Any, Optional
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, OutgoingApiCall, Repository
from src.config.enums import SymbolKindEnum, LanguageEnum
from src.utils.logging_config import get_logger
from src.parsers.javascript_parser import JavaScriptParser

logger = get_logger(__name__)


class OutgoingCallExtractor:
    """Extracts outgoing API calls from parsed code."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.js_parser = JavaScriptParser()
    
    async def extract_calls(self, repository_id: int) -> int:
        """
        Extract outgoing API calls from a repository.
        
        Args:
            repository_id: Repository ID
            
        Returns:
            Number of calls extracted
        """
        calls_extracted = 0
        
        # Get all files in repository
        result = await self.session.execute(
            select(File)
            .where(File.repository_id == repository_id)
        )
        files = result.scalars().all()
        
        for file in files:
            try:
                # We need to read the file content again as it's not stored in DB (except chunks)
                # But we can try to use the file path if available
                # In a real scenario, we might want to pass the content or path
                # For now, we'll skip if we can't access the file
                # But wait, the task has access to the repo path. 
                # We should probably refactor to accept repo_path or read from disk
                pass
            except Exception as e:
                logger.error(f"Failed to process file {file.path}: {e}")
                
        return calls_extracted

    async def extract_from_file(self, file: File, repo_path: Any, content: Optional[str] = None) -> List[OutgoingApiCall]:
        """
        Extract calls from a single file.
        
        Args:
            file: File model
            repo_path: Path to repository root
            content: Optional file content (if already read)
            
        Returns:
            List of OutgoingApiCall objects
        """
        logger.debug(
            "outgoing_call_extraction_started",
            file_id=file.id,
            file_path=file.path,
            language=file.language
        )
        
        calls = []
        file_path = repo_path / file.path
        
        try:
            if content is None:
                if not file_path.exists():
                    return []
                content = file_path.read_text(encoding='utf-8-sig', errors='ignore')
            
            if file.language == LanguageEnum.CSHARP:
                calls.extend(self._extract_csharp_calls(content, file))
            elif file.language in [LanguageEnum.JAVASCRIPT, LanguageEnum.TYPESCRIPT]:
                calls.extend(self._extract_js_calls(content, file))
                
        except Exception as e:
            logger.error(f"Error extracting calls from {file.path}: {e}")
            
        return calls

    def _extract_csharp_calls(self, content: str, file: File) -> List[OutgoingApiCall]:
        """Extract HTTP calls from C# code."""
        calls = []
        
        # Simplified URL pattern to avoid catastrophic backtracking
        # Old pattern (?:{[^}]*}|[^"'])*  caused exponential time on certain inputs
        # New pattern is simpler and faster - just match non-quote characters
        # This handles most URLs including interpolated strings like $"{baseUrl}/api"
        URL_CONTENT_PATTERN = r'[^"\']+?'
        
        # Regex patterns for C# HttpClient
        # HttpClient.GetAsync("url")
        # client.PostAsync("url", content)
        # client.PostAsJsonAsync("url", content)
        # Note: Using non-greedy [^)]+ to match arguments before URL
        patterns = [
            (rf'\.GetAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'GET', 'HttpClient'),
            (rf'\.PostAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'POST', 'HttpClient'),
            (rf'\.PutAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'PUT', 'HttpClient'),
            (rf'\.DeleteAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'DELETE', 'HttpClient'),
            (rf'\.PatchAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'PATCH', 'HttpClient'),
            # ServiceStack / Generic Clients (Get<T>, Post<T>, etc without Async)
            (rf'\.Get\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'GET', 'ServiceStack'),
            (rf'\.Post\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'POST', 'ServiceStack'),
            (rf'\.Put\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'PUT', 'ServiceStack'),
            (rf'\.Delete\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'DELETE', 'ServiceStack'),
            (rf'\.Patch\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'PATCH', 'ServiceStack'),
            # JSON Extensions
            (rf'\.GetFromJsonAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'GET', 'HttpClient.Json'),
            (rf'\.PostAsJsonAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'POST', 'HttpClient.Json'),
            (rf'\.PutAsJsonAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'PUT', 'HttpClient.Json'),
            # RestSharp
            # Capture Method if present: new RestRequest("url", Method.POST)
            (rf'new\s+RestRequest\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\'](?:[^)]*?Method\.(\w+))?', 'UNKNOWN', 'RestSharp'),
            # Refit
            (rf'\[Get\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']\s*\)\]', 'GET', 'Refit'),
            (rf'\[Post\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']\s*\)\]', 'POST', 'Refit'),
            (rf'\[Put\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']\s*\)\]', 'PUT', 'Refit'),
            (rf'\[Delete\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']\s*\)\]', 'DELETE', 'Refit'),
            # Flurl: "url".GetAsync()
            (rf'["\']({URL_CONTENT_PATTERN})["\']\s*\.\s*GetAsync', 'GET', 'Flurl'),
            (rf'["\']({URL_CONTENT_PATTERN})["\']\s*\.\s*PostJsonAsync', 'POST', 'Flurl'),
            (rf'["\']({URL_CONTENT_PATTERN})["\']\s*\.\s*PostUrlEncodedAsync', 'POST', 'Flurl'),
            # OData: client.Execute<T>(new Uri("url", ...))
            (rf'\.Execute(?:Async)?\s*(?:<[^>]+>)?\s*\(\s*new\s+Uri\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', 'GET', 'OData'),
        ]
        
        for pattern, method, library in patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                url = match.group(1)
                line_number = content[:match.start()].count('\n') + 1
                
                # Use a local variable for the method to avoid modifying the loop variable
                call_method = method
                
                # Refine RestSharp method
                if library == 'RestSharp' and call_method == 'UNKNOWN':
                    # Check if we captured a method in group 2
                    # We can safely access group 2 because the regex has it
                    captured_method = match.group(2)
                    if captured_method:
                        call_method = captured_method.upper()
                    else:
                        call_method = 'GET'
                
                calls.append(OutgoingApiCall(
                    repository_id=file.repository_id,
                    file_id=file.id,
                    http_method=call_method,
                    url_pattern=url,
                    call_type="backend_to_backend",
                    http_client_library=library,
                    line_number=line_number,
                    is_dynamic_url=0 if '{' not in url and '$' not in url else 1
                ))

        # Generic Wrapper Pattern
        # Matches Http(Verb)...(... "url" ...)
        # Captures the first string literal in the arguments as the URL
        # IMPORTANT: Use negative lookbehind to exclude [HttpGet(...)] attributes
        generic_pattern = rf'(?<!\[)Http(Get|Post|Put|Delete|Patch)\w*\s*(?:<[^>]+>)?\s*\([^)]*?(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(generic_pattern, content, re.DOTALL):
            method = match.group(1).upper()
            url = match.group(2)
            line_number = content[:match.start()].count('\n') + 1
            
            # Additional validation: skip if line starts with '[' (attribute)
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_text = content[line_start:match.start()].strip()
            if line_text.startswith('['):
                continue
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method=method,
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="GenericWrapper",
                line_number=line_number,
                is_dynamic_url=0 if '{' not in url and '$' not in url else 1
            ))


        # Fluent Builder Pattern (e.g., webApiClient.Post<T>(request))
        # Pattern: webApiClient.Post<ResponseDto>(request)
        # Note: Added (?!["\']) to exclude calls where the first argument is a string literal (handled by other patterns)
        fluent_api_pattern = r'(\w+)\.(Get|Post|Put|Delete|Patch)\s*<[^>]+>\s*\(\s*(?!["\'])'
        for match in re.finditer(fluent_api_pattern, content):
            client_var = match.group(1)
            method = match.group(2).upper()
            line_number = content[:match.start()].count('\n') + 1
            
            # Try to find the .FromUrl() call in the same or previous lines (within 10 lines)
            search_start = max(0, content.rfind('\n', 0, match.start()) - 1000)  # Search 1000 chars back
            search_text = content[search_start:match.end()]
            
            # Look for .FromUrl("...") or .FromUrl($"...")
            url_match = re.search(rf'\.FromUrl\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']', search_text)
            
            if url_match:
                url = url_match.group(1)
            else:
                # No URL found, mark as dynamic
                url = f"{client_var}.{method.lower()}://dynamic"
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method=method,
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="FluentApiPattern",
                line_number=line_number,
                is_dynamic_url=1 if '{' in url or '$' in url or 'dynamic' in url else 0
            ))

        # Handle SendAsync with HttpRequestMessage
        # new HttpRequestMessage(HttpMethod.Post, "url")
        send_pattern = rf'new\s+HttpRequestMessage\s*\(\s*HttpMethod\.(\w+)\s*,\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(send_pattern, content):
            method = match.group(1).upper()
            url = match.group(2)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method=method,
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="HttpClient.SendAsync",
                line_number=line_number,
                is_dynamic_url=0 if '{' not in url and '$' not in url else 1
            ))

        # ========== gRPC Client Calls (High Priority) ==========
        # GrpcChannel.ForAddress("https://localhost:5001")
        grpc_channel_pattern = rf'GrpcChannel\.ForAddress\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(grpc_channel_pattern, content):
            url = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="GRPC",
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="Grpc.Net.Client",
                line_number=line_number,
                is_dynamic_url=0 if '{' not in url and '$' not in url else 1
            ))

        # new GreeterClient(channel) - gRPC generated client
        grpc_client_pattern = r'new\s+(\w+Client)\s*\(\s*channel\s*\)'
        for match in re.finditer(grpc_client_pattern, content):
            client_name = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="GRPC",
                url_pattern=f"grpc://{client_name}",
                call_type="backend_to_backend",
                http_client_library="Grpc.Core",
                line_number=line_number,
                is_dynamic_url=0
            ))

        # ========== GraphQL Client Calls (Medium Priority) ==========
        # GraphQLHttpClient or StrawberryShake patterns
        # new GraphQLHttpClient("https://api.example.com/graphql", ...)
        graphql_client_pattern = rf'new\s+GraphQLHttpClient\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(graphql_client_pattern, content):
            url = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="GRAPHQL",
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="GraphQL.Client",
                line_number=line_number,
                is_dynamic_url=0 if '{' not in url and '$' not in url else 1
            ))

        # ExecuteAsync<T> - GraphQL query execution (StrawberryShake)
        graphql_execute_pattern = r'\.ExecuteAsync\s*<[^>]+>\s*\('
        for match in re.finditer(graphql_execute_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="GRAPHQL",
                url_pattern="graphql://query",
                call_type="backend_to_backend",
                http_client_library="StrawberryShake",
                line_number=line_number,
                is_dynamic_url=0
            ))

        # SendQueryAsync<T> - GraphQL query execution (GraphQL.Client)
        graphql_send_pattern = r'\.SendQueryAsync\s*<[^>]+>\s*\('
        for match in re.finditer(graphql_send_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="GRAPHQL",
                url_pattern="graphql://query",
                call_type="backend_to_backend",
                http_client_library="GraphQL.Client",
                line_number=line_number,
                is_dynamic_url=0
            ))

        # ========== SignalR Hub Connections (Medium Priority) ==========
        # new HubConnectionBuilder().WithUrl("https://example.com/hub")
        signalr_url_pattern = rf'\.WithUrl\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(signalr_url_pattern, content):
            url = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="SIGNALR",
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="SignalR.Client",
                line_number=line_number,
                is_dynamic_url=0 if '{' not in url and '$' not in url else 1
            ))

        # connection.InvokeAsync("MethodName", ...)
        signalr_invoke_pattern = rf'\.InvokeAsync\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(signalr_invoke_pattern, content):
            method_name = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="SIGNALR",
                url_pattern=f"signalr://{method_name}",
                call_type="backend_to_backend",
                http_client_library="SignalR.Client",
                line_number=line_number,
                is_dynamic_url=0
            ))

        # connection.On("MethodName", handler)
        signalr_on_pattern = rf'\.On\s*(?:<[^>]+>)?\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(signalr_on_pattern, content):
            method_name = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="SIGNALR",
                url_pattern=f"signalr://{method_name}",
                call_type="backend_to_backend",
                http_client_library="SignalR.Client",
                line_number=line_number,
                is_dynamic_url=0
            ))

        # ========== WebSocket Connections (Low Priority) ==========
        # ConnectAsync(new Uri("ws://example.com"))
        websocket_connect_pattern = rf'ConnectAsync\s*\(\s*new\s+Uri\s*\(\s*(?:\$)?["\']({URL_CONTENT_PATTERN})["\']'
        for match in re.finditer(websocket_connect_pattern, content):
            url = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="WEBSOCKET",
                url_pattern=url,
                call_type="backend_to_backend",
                http_client_library="ClientWebSocket",
                line_number=line_number,
                is_dynamic_url=0 if '{' not in url and '$' not in url else 1
            ))

        # new ClientWebSocket() - track instantiation
        websocket_new_pattern = r'new\s+ClientWebSocket\s*\(\s*\)'
        for match in re.finditer(websocket_new_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            calls.append(OutgoingApiCall(
                repository_id=file.repository_id,
                file_id=file.id,
                http_method="WEBSOCKET",
                url_pattern="ws://connection",
                call_type="backend_to_backend",
                http_client_library="ClientWebSocket",
                line_number=line_number,
                is_dynamic_url=0
            ))
                
        # Sort calls by line number to ensure consistent order
        calls.sort(key=lambda x: x.line_number)
        
        return calls

    def _extract_js_calls(self, content: str, file: File) -> List[OutgoingApiCall]:
        """Extract HTTP calls from JS/TS code using AST parser."""
        calls = []
        
        try:
            # Parse code using JavaScriptParser which now includes API call extraction
            parse_result = self.js_parser.parse(content, file.path)
            
            for api_call in parse_result.api_calls:
                calls.append(OutgoingApiCall(
                    repository_id=file.repository_id,
                    file_id=file.id,
                    http_method=api_call.get('http_method', 'UNKNOWN'),
                    url_pattern=api_call.get('url_pattern', ''),
                    call_type=api_call.get('call_type', 'frontend_to_backend'),
                    http_client_library=api_call.get('http_client_library', 'unknown'),
                    line_number=api_call.get('line_number', 0),
                    is_dynamic_url=1 if api_call.get('is_dynamic_url', False) else 0,
                    context_metadata=api_call.get('context_metadata')
                ))
                
        except Exception as e:
            logger.error(f"Error parsing JS calls in {file.path}: {e}")
            # Fallback to regex if AST parsing fails? 
            # For now, let's trust the parser or return empty list to avoid duplicates if we mixed approaches
            
        return calls
