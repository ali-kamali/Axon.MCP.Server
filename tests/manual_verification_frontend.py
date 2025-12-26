import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.parsers.javascript_parser import JavaScriptParser

def test_frontend_extraction():
    print("\n--- Testing Frontend Framework Extraction ---")
    parser = JavaScriptParser()
    
    code = """
    import { useQuery, useMutation } from 'react-query';
    import useSWR from 'swr';
    import { useQuery as useApolloQuery, gql } from '@apollo/client';
    
    const GET_DOGS = gql`
      query GetDogs {
        dogs {
          id
          breed
        }
      }
    `;

    async function MyComponent() {
        // React Query
        const { data } = useQuery(['todos'], fetchTodos);
        const mutation = useMutation(newTodo => axios.post('/todos', newTodo));
        
        // SWR
        const { data: user } = useSWR('/api/user', fetcher);
        
        // Apollo Client
        const { loading, error, data } = useApolloQuery(GET_DOGS);
        
        // Nuxt 3
        const { data: count } = useFetch('/api/count');
        const users = $fetch('/api/users');
        
        // RTK Query
        const api = createApi({
            baseQuery: fetchBaseQuery({ baseUrl: '/api/rtk' }),
            endpoints: (builder) => ({
                getPokemon: builder.query({
                    query: (name) => `pokemon/${name}`,
                }),
            }),
        });
    }
    """
    
    result = parser.parse(code, "test_frontend.js")
    
    print(f"Found {len(result.api_calls)} API calls:")
    for call in result.api_calls:
        print(f"- {call['http_client_library']} {call['http_method']} {call['url_pattern']}")
        
    expected_calls = 9 # 7 previous + 2 RTK Query (createApi + fetchBaseQuery)
    if len(result.api_calls) == expected_calls:
        print("[PASS] Frontend Extraction Passed")
    else:
        print(f"[FAIL] Frontend Extraction Failed (Expected {expected_calls}, got {len(result.api_calls)})")

if __name__ == "__main__":
    test_frontend_extraction()
