
import unittest
from unittest.mock import MagicMock
import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

# Mock dependencies before importing the extractor
sys.modules['src.database.models'] = MagicMock()
sys.modules['src.config.enums'] = MagicMock()
sys.modules['src.utils.logging_config'] = MagicMock()
sys.modules['src.parsers.javascript_parser'] = MagicMock()

# Define dummy model for OutgoingApiCall to allow attribute access
class OutgoingApiCall:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

models_mock = MagicMock()
models_mock.OutgoingApiCall = OutgoingApiCall
sys.modules['src.database.models'] = models_mock

from src.extractors.outgoing_call_extractor import OutgoingCallExtractor

class TestOutgoingCallPatterns(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.extractor = OutgoingCallExtractor(self.session)
        self.file_mock = MagicMock()
        self.file_mock.repository_id = 1
        self.file_mock.id = 1

    def _extract(self, content):
        return self.extractor._extract_csharp_calls(content, self.file_mock)

    def test_http_client_standard_methods(self):
        content = """
        await client.GetAsync("api/users");
        await client.PostAsync("api/users", content);
        await client.PutAsync("api/users/1", content);
        await client.DeleteAsync("api/users/1");
        await client.PatchAsync("api/users/1", content);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls[0].http_method, 'GET')
        self.assertEqual(calls[0].url_pattern, 'api/users')
        self.assertEqual(calls[1].http_method, 'POST')
        self.assertEqual(calls[4].http_method, 'PATCH')

    def test_http_client_json_extensions(self):
        content = """
        await client.GetFromJsonAsync<User>("api/users/1");
        await client.PostAsJsonAsync("api/users", user);
        await client.PutAsJsonAsync("api/users/1", user);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].http_client_library, 'HttpClient.Json')
        self.assertEqual(calls[0].url_pattern, 'api/users/1')

    def test_rest_sharp(self):
        content = """
        var request = new RestRequest("api/users", Method.GET);
        var req2 = new RestRequest("api/items", Method.POST);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].http_client_library, 'RestSharp')
        self.assertEqual(calls[0].url_pattern, 'api/users')
        self.assertEqual(calls[1].http_method, 'POST')

    def test_refit_attributes(self):
        content = """
        [Get("/users/{id}")]
        Task<User> GetUser(int id);
        
        [Post("/users")]
        Task CreateUser([Body] User user);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].http_client_library, 'Refit')
        self.assertEqual(calls[0].url_pattern, '/users/{id}')
        self.assertEqual(calls[0].is_dynamic_url, 1)

    def test_generic_wrapper(self):
        content = """
        // Wrapper usage
        _api.HttpGet<User>("api/users/1");
        _api.HttpPost("api/users", data);
        
        // Should NOT match attributes
        [HttpGet("route")]
        public void Action() { }
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].http_client_library, 'GenericWrapper')
        self.assertEqual(calls[0].url_pattern, 'api/users/1')

    def test_fluent_pattern_interpolated_nested_quotes(self):
        # The specific issue we fixed
        content = """
        requestSpecificationBuilder.FromUrl(
            $"{configuration["IdentityUrlExternalApi"]}{BaseUserInfoUrlPath}/{userId}/Claims")
            .Build();
        
        webApiClient.Get<GetClaims>(request);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].http_client_library, 'FluentApiPattern')
        expected_url = '{configuration["IdentityUrlExternalApi"]}{BaseUserInfoUrlPath}/{userId}/Claims'
        self.assertEqual(calls[0].url_pattern, expected_url)

    def test_fluent_pattern_simple(self):
        content = """
        builder.FromUrl("api/simple").Build();
        client.Post<Dto>(req);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/simple')

    def test_http_request_message(self):
        content = """
        var msg = new HttpRequestMessage(HttpMethod.Get, "api/test");
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].http_client_library, 'HttpClient.SendAsync')
        self.assertEqual(calls[0].url_pattern, 'api/test')

    def test_grpc_channel(self):
        content = """
        var channel = GrpcChannel.ForAddress("https://localhost:5001");
        var client = new GreeterClient(channel);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].http_client_library, 'Grpc.Net.Client')
        self.assertEqual(calls[0].url_pattern, 'https://localhost:5001')
        self.assertEqual(calls[1].http_client_library, 'Grpc.Core')
        self.assertEqual(calls[1].url_pattern, 'grpc://GreeterClient')

    def test_graphql(self):
        content = """
        var client = new GraphQLHttpClient("https://api.graphql.com");
        await client.ExecuteAsync<Response>(request);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].http_client_library, 'GraphQL.Client')
        self.assertEqual(calls[1].http_client_library, 'StrawberryShake')

    def test_signalr(self):
        content = """
        var conn = new HubConnectionBuilder().WithUrl("https://chat").Build();
        await conn.InvokeAsync("SendMessage", "user", "hi");
        conn.On("ReceiveMessage", (u, m) => {});
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].http_method, 'SIGNALR')
        self.assertEqual(calls[0].url_pattern, 'https://chat')
        self.assertEqual(calls[1].url_pattern, 'signalr://SendMessage')
        self.assertEqual(calls[2].url_pattern, 'signalr://ReceiveMessage')

    def test_websockets(self):
        content = """
        var ws = new ClientWebSocket();
        await ws.ConnectAsync(new Uri("ws://server"), token);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].http_method, 'WEBSOCKET')
        self.assertEqual(calls[0].url_pattern, 'ws://connection') # Instantiation
        self.assertEqual(calls[1].url_pattern, 'ws://server') # Connect

    def test_complex_interpolation(self):
        # Test nested braces and mixed quotes
        content = """
        client.GetAsync($"api/{config["v1"]}/{obj.GetId()}/data");
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/{config["v1"]}/{obj.GetId()}/data')

    def test_url_concatenation(self):
        # High Priority: String concatenation
        content = """
        await client.GetAsync(baseUrl + "/api/users");
        await client.PostAsync("api/" + "v1" + "/users", content);
        """
        calls = self._extract(content)
        # We expect to extract the string literals found in the first argument
        # Ideally: "/api/users" and "api/" (or "v1", "/users")
        # Current regex might fail if it expects quote immediately after (
        self.assertTrue(len(calls) >= 2)
        # We might extract partials, which is acceptable for regex
        self.assertIn("/api/users", [c.url_pattern for c in calls])
        self.assertIn("api/", [c.url_pattern for c in calls])

    def test_flurl_pattern(self):
        # Medium Priority: Flurl library
        content = """
        await "https://api.example.com".GetAsync();
        await "https://api.example.com".PostJsonAsync(data);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].url_pattern, 'https://api.example.com')
        self.assertEqual(calls[1].url_pattern, 'https://api.example.com')

    def test_typed_http_client(self):
        # Medium Priority: Typed HttpClient (fields)
        content = """
        private readonly HttpClient _client;
        public async Task Get() {
            await _client.GetAsync("api/users");
        }
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_send_async_inline(self):
        # High Priority: SendAsync with inline request
        content = """
        await client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "api/users"));
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_rest_sharp_execute(self):
        # High Priority: RestSharp Execute
        content = """
        var request = new RestRequest("api/users");
        client.Execute(request);
        client.ExecuteAsync(request);
        """
        # We already capture 'new RestRequest'. 
        # Capturing Execute might be redundant if we don't know the URL.
        # But let's see if we capture the creation.
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].http_client_library, 'RestSharp')
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_query_parameters(self):
        # High Priority: Query parameters
        content = """
        await client.GetAsync("api/users?page=1&limit=10");
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users?page=1&limit=10')

    def test_servicestack_client(self):
        # ServiceStack: client.Get<T>("url")
        content = """
        var client = new JsonServiceClient("https://api.example.com");
        var response = client.Get<User>("/users/1");
        var response2 = client.Post<User>("/users", new User());
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].url_pattern, '/users/1')
        self.assertEqual(calls[0].http_client_library, 'ServiceStack')
        self.assertEqual(calls[1].url_pattern, '/users')
        self.assertEqual(calls[1].http_client_library, 'ServiceStack')

    def test_odata_client(self):
        # OData: client.Execute<T>(uri)
        content = """
        var client = new DataServiceContext(new Uri("https://api.example.com/odata"));
        var users = client.Execute<User>(new Uri("Users", UriKind.Relative));
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'Users')
        self.assertEqual(calls[0].http_client_library, 'OData')

    def test_polly_policy(self):
        # Polly: Policy.ExecuteAsync(() => client.GetAsync("url"))
        content = """
        await policy.ExecuteAsync(async () => 
            await client.GetAsync("api/users"));
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_http_client_options(self):
        # Headers, Timeout, Auth, etc. shouldn't break extraction
        content = """
        client.DefaultRequestHeaders.Add("X-API-Key", "key");
        client.Timeout = TimeSpan.FromSeconds(30);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        
        var request = new HttpRequestMessage(HttpMethod.Get, "api/users");
        request.Version = HttpVersion.Version20;
        request.Properties["CustomKey"] = "CustomValue";
        
        await client.SendAsync(request);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_using_statement(self):
        # HttpClient in using block
        content = """
        using (var client = new HttpClient())
        {
            await client.GetAsync("api/users");
        }
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_refit_complex(self):
        # Refit with Query/Path params
        content = """
        public interface IUserApi
        {
            [Get("/users/{userId}/posts/{postId}")]
            Task<Post> GetUserPost(int userId, int postId);
            
            [Get("/users")]
            Task<List<User>> GetUsers([Query] int page, [Query] int limit);
        }
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].url_pattern, '/users/{userId}/posts/{postId}')
        self.assertEqual(calls[1].url_pattern, '/users')

    def test_multiple_clients(self):
        # Multiple instances
        content = """
        var userClient = new HttpClient();
        var orderClient = new HttpClient();
        await userClient.GetAsync("/users");
        await orderClient.GetAsync("/orders");
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].url_pattern, '/users')
        self.assertEqual(calls[1].url_pattern, '/orders')

    def test_extension_methods(self):
        # Custom extension methods wrapping HttpClient
        # This might be hard to detect generically unless we track the type of 'client'
        # But if they use standard naming like GetAsync<T>, we might catch it.
        content = """
        await client.GetAsync<User>("api/users/1");
        """
        # Our generic wrapper pattern might catch this if it matches .GetAsync<T>(...)
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users/1')

    def test_graphql_variables(self):
        # GraphQL with variables
        content = """
        var request = new GraphQLRequest
        {
            Query = "query...",
            Variables = new { id = 123 }
        };
        await client.SendQueryAsync<UserResponse>(request);
        """
        # We don't extract the URL here because it's usually configured in the client.
        # But we should extract the call type.
        # Current extractor looks for `new GraphQLHttpClient("url")`
        # or `.ExecuteAsync`.
        # `SendQueryAsync` is another method.
        calls = self._extract(content)
        # If we support SendQueryAsync, we should find 1 call.
        # If not, 0.
        # Let's assume we want to support it.
        # For now, let's assert 0 if we haven't added it, or 1 if we add it.
        # I'll add support for SendQueryAsync in the extractor.
        # So I expect 1.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].http_method, 'GRAPHQL')

    def test_signalr_auth(self):
        # SignalR with auth options
        content = """
        var connection = new HubConnectionBuilder()
            .WithUrl("https://chat", options => { ... })
            .Build();
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'https://chat')

    # Phase 2: Additional Coverage Tests

    def test_send_async_separated_request(self):
        # High Priority: HttpClient.SendAsync with separated request
        content = """
        var request = new HttpRequestMessage(HttpMethod.Get, "api/users");
        request.Headers.Add("X-Custom", "value");
        var response = await client.SendAsync(request);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')
        self.assertEqual(calls[0].http_method, 'GET')
        self.assertEqual(calls[0].http_client_library, 'HttpClient.SendAsync')

    def test_rest_sharp_execute_verified(self):
        # High Priority: Verify RestSharp Execute works with request creation
        content = """
        var request = new RestRequest("api/users", Method.POST);
        var response = await client.ExecuteAsync(request);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')
        self.assertEqual(calls[0].http_method, 'POST')

    def test_send_async_with_cancellation_token(self):
        # Medium Priority: Cancellation tokens with various methods
        content = """
        await client.GetAsync("api/users", cancellationToken);
        await client.PostAsync("api/users", content, cancellationToken);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].url_pattern, 'api/users')
        self.assertEqual(calls[1].url_pattern, 'api/users')

    def test_http_completion_option_verified(self):
        # Medium Priority: HttpCompletionOption patterns
        content = """
        var request = new HttpRequestMessage(HttpMethod.Get, "api/users");
        var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users')

    def test_query_string_interpolation_verified(self):
        # Medium Priority: Interpolated query strings
        content = """
        await client.GetAsync($"api/users?page={page}&limit={limit}");
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url_pattern, 'api/users?page={page}&limit={limit}')
        self.assertEqual(calls[0].is_dynamic_url, 1)

    def test_flurl_simple_verified(self):
        # Medium Priority: Flurl simple patterns
        content = """
        var result1 = await "https://api.example.com".GetAsync();
        var result2 = await "https://api.example.com/api/users".GetAsync();
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        self.assertIn('https://api.example.com', [c.url_pattern for c in calls])

    def test_grpc_client_verified(self):
        # Low Priority: gRPC client creation
        content = """
        var client = new GreeterClient(channel);
        var response = await client.SayHelloAsync(new HelloRequest { Name = "World" });
        """
        calls = self._extract(content)
        self.assertTrue(len(calls) >= 1)
        self.assertEqual(calls[0].http_client_library, 'Grpc.Core')

    def test_websocket_with_options_verified(self):
        # Low Priority: WebSocket with options
        content = """
        var ws = new ClientWebSocket();
        ws.Options.AddSubProtocol("chat");
        await ws.ConnectAsync(new Uri("ws://server"), cancellationToken);
        """
        calls = self._extract(content)
        self.assertEqual(len(calls), 2)
        ws_calls = [c for c in calls if c.http_method == 'WEBSOCKET']
        self.assertEqual(len(ws_calls), 2)

if __name__ == '__main__':
    unittest.main()
