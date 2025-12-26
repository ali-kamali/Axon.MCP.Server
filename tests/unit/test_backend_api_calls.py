"""
Unit tests for backend-to-backend API call detection.
Tests gRPC, GraphQL, SignalR, and WebSocket pattern detection.
"""

import pytest
from src.extractors.outgoing_call_extractor import OutgoingCallExtractor
from src.database.models import File
from src.config.enums import LanguageEnum


class MockFile:
    """Mock File object for testing."""
    def __init__(self, repository_id=1, file_id=1, language=LanguageEnum.CSHARP):
        self.id = file_id
        self.repository_id = repository_id
        self.language = language
        self.path = "test.cs"


class TestGrpcDetection:
    """Test gRPC client call detection."""
    
    def test_grpc_channel_for_address(self):
        """Test detection of GrpcChannel.ForAddress pattern."""
        code = '''
        var channel = GrpcChannel.ForAddress("https://localhost:5001");
        var client = new GreeterClient(channel);
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        grpc_calls = [c for c in calls if c.http_client_library == "Grpc.Net.Client"]
        assert len(grpc_calls) == 1
        assert grpc_calls[0].url_pattern == "https://localhost:5001"
        assert grpc_calls[0].http_method == "GRPC"
        assert grpc_calls[0].call_type == "backend_to_backend"
    
    def test_grpc_generated_client(self):
        """Test detection of gRPC generated client instantiation."""
        code = '''
        var channel = CreateChannel();
        var greeterClient = new GreeterClient(channel);
        var orderClient = new OrderServiceClient(channel);
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        grpc_calls = [c for c in calls if c.http_client_library == "Grpc.Core"]
        assert len(grpc_calls) == 2
        assert grpc_calls[0].url_pattern == "grpc://GreeterClient"
        assert grpc_calls[1].url_pattern == "grpc://OrderServiceClient"
        assert all(c.http_method == "GRPC" for c in grpc_calls)


class TestGraphQLDetection:
    """Test GraphQL client call detection."""
    
    def test_graphql_http_client(self):
        """Test detection of GraphQLHttpClient pattern."""
        code = '''
        var client = new GraphQLHttpClient("https://api.example.com/graphql", new NewtonsoftJsonSerializer());
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        graphql_calls = [c for c in calls if c.http_client_library == "GraphQL.Client"]
        assert len(graphql_calls) == 1
        assert graphql_calls[0].url_pattern == "https://api.example.com/graphql"
        assert graphql_calls[0].http_method == "GRAPHQL"
        assert graphql_calls[0].call_type == "backend_to_backend"
    
    def test_strawberry_shake_execute_async(self):
        """Test detection of StrawberryShake ExecuteAsync pattern."""
        code = '''
        var result = await client.ExecuteAsync<GetUsersQuery>();
        var data = await myClient.ExecuteAsync<GetOrdersQuery>();
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        graphql_calls = [c for c in calls if c.http_client_library == "StrawberryShake"]
        assert len(graphql_calls) == 2
        assert all(c.url_pattern == "graphql://query" for c in graphql_calls)
        assert all(c.http_method == "GRAPHQL" for c in graphql_calls)


class TestSignalRDetection:
    """Test SignalR hub connection detection."""
    
    def test_signalr_with_url(self):
        """Test detection of SignalR WithUrl pattern."""
        code = '''
        var connection = new HubConnectionBuilder()
            .WithUrl("https://example.com/chathub")
            .Build();
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        signalr_calls = [c for c in calls if c.http_client_library == "SignalR.Client" and "example.com" in c.url_pattern]
        assert len(signalr_calls) == 1
        assert signalr_calls[0].url_pattern == "https://example.com/chathub"
        assert signalr_calls[0].http_method == "SIGNALR"
    
    def test_signalr_invoke_async(self):
        """Test detection of SignalR InvokeAsync pattern."""
        code = '''
        await connection.InvokeAsync("SendMessage", user, message);
        await hubConnection.InvokeAsync<string>("GetData", id);
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        signalr_calls = [c for c in calls if c.http_client_library == "SignalR.Client" and "signalr://" in c.url_pattern]
        assert len(signalr_calls) >= 2
        
        send_message_calls = [c for c in signalr_calls if "SendMessage" in c.url_pattern]
        get_data_calls = [c for c in signalr_calls if "GetData" in c.url_pattern]
        
        assert len(send_message_calls) == 1
        assert len(get_data_calls) == 1
        assert send_message_calls[0].url_pattern == "signalr://SendMessage"
        assert get_data_calls[0].url_pattern == "signalr://GetData"
    
    def test_signalr_on_handler(self):
        """Test detection of SignalR On pattern."""
        code = '''
        connection.On("ReceiveMessage", (string user, string message) => {
            Console.WriteLine($"{user}: {message}");
        });
        connection.On<User>("UserConnected", user => HandleUser(user));
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        signalr_calls = [c for c in calls if c.http_client_library == "SignalR.Client" and "signalr://" in c.url_pattern]
        
        receive_calls = [c for c in signalr_calls if "ReceiveMessage" in c.url_pattern]
        user_connected_calls = [c for c in signalr_calls if "UserConnected" in c.url_pattern]
        
        assert len(receive_calls) == 1
        assert len(user_connected_calls) == 1
        assert receive_calls[0].url_pattern == "signalr://ReceiveMessage"
        assert user_connected_calls[0].url_pattern == "signalr://UserConnected"


class TestWebSocketDetection:
    """Test WebSocket connection detection."""
    
    def test_websocket_connect_async(self):
        """Test detection of WebSocket ConnectAsync pattern."""
        code = '''
        var ws = new ClientWebSocket();
        await ws.ConnectAsync(new Uri("ws://localhost:8080/ws"), CancellationToken.None);
        await client.ConnectAsync(new Uri("wss://api.example.com/socket"), token);
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        ws_calls = [c for c in calls if c.http_client_library == "ClientWebSocket" and c.url_pattern.startswith("ws")]
        assert len(ws_calls) >= 2
        
        localhost_calls = [c for c in ws_calls if "localhost" in c.url_pattern]
        api_calls = [c for c in ws_calls if "api.example.com" in c.url_pattern]
        
        assert len(localhost_calls) == 1
        assert len(api_calls) == 1
        assert localhost_calls[0].url_pattern == "ws://localhost:8080/ws"
        assert api_calls[0].url_pattern == "wss://api.example.com/socket"
        assert all(c.http_method == "WEBSOCKET" for c in ws_calls)
    
    def test_websocket_instantiation(self):
        """Test detection of WebSocket instantiation."""
        code = '''
        var websocket = new ClientWebSocket();
        using var ws = new ClientWebSocket();
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        ws_calls = [c for c in calls if c.http_client_library == "ClientWebSocket" and c.url_pattern == "ws://connection"]
        assert len(ws_calls) == 2
        assert all(c.http_method == "WEBSOCKET" for c in ws_calls)


class TestMixedPatterns:
    """Test detection of multiple patterns in the same file."""
    
    def test_multiple_backend_patterns(self):
        """Test detection when multiple backend communication patterns are present."""
        code = '''
        public class CommunicationService
        {
            private readonly HttpClient _httpClient;
            private readonly ClientWebSocket _websocket;
            
            public async Task InitializeAsync()
            {
                // HTTP call
                await _httpClient.GetAsync("https://api.example.com/data");
                
                // gRPC
                var channel = GrpcChannel.ForAddress("https://grpc.example.com");
                var client = new UserServiceClient(channel);
                
                // GraphQL
                var graphqlClient = new GraphQLHttpClient("https://api.example.com/graphql", serializer);
                
                // SignalR
                var hubConnection = new HubConnectionBuilder()
                    .WithUrl("https://example.com/hub")
                    .Build();
                await hubConnection.InvokeAsync("Notify", "message");
                
                // WebSocket
                var ws = new ClientWebSocket();
                await ws.ConnectAsync(new Uri("wss://example.com/ws"), token);
            }
        }
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        # Should detect all different types
        http_calls = [c for c in calls if c.http_client_library == "HttpClient"]
        grpc_calls = [c for c in calls if "Grpc" in c.http_client_library]
        graphql_calls = [c for c in calls if c.http_method == "GRAPHQL"]
        signalr_calls = [c for c in calls if c.http_client_library == "SignalR.Client"]
        ws_calls = [c for c in calls if c.http_client_library == "ClientWebSocket"]
        
        assert len(http_calls) >= 1
        assert len(grpc_calls) >= 1
        assert len(graphql_calls) >= 1
        assert len(signalr_calls) >= 1
        assert len(ws_calls) >= 1
        
        # All should be backend_to_backend
        assert all(c.call_type == "backend_to_backend" for c in calls)


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_dynamic_urls(self):
        """Test detection of dynamic URLs with placeholders."""
        code = '''
        var channel = GrpcChannel.ForAddress("https://{host}:5001");
        var client = new GraphQLHttpClient("https://api.{domain}/graphql", serializer);
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        grpc_calls = [c for c in calls if c.http_client_library == "Grpc.Net.Client"]
        graphql_calls = [c for c in calls if c.http_client_library == "GraphQL.Client"]
        
        # Dynamic URLs with placeholders should be detected
        assert len(grpc_calls) >= 1
        assert len(graphql_calls) >= 1
        
        # Should be marked as dynamic (contains {})
        assert any(c.is_dynamic_url == 1 for c in grpc_calls)
        assert any(c.is_dynamic_url == 1 for c in graphql_calls)
    
    def test_multiline_patterns(self):
        """Test detection across multiple lines."""
        code = '''
        var connection = new HubConnectionBuilder()
            .WithUrl(
                "https://example.com/hub"
            )
            .WithAutomaticReconnect()
            .Build();
        '''
        
        extractor = OutgoingCallExtractor(None)
        file = MockFile()
        calls = extractor._extract_csharp_calls(code, file)
        
        signalr_calls = [c for c in calls if c.http_client_library == "SignalR.Client"]
        assert len(signalr_calls) >= 1
        assert any("example.com/hub" in c.url_pattern for c in signalr_calls)
