
if __name__ == "__main__":
    try:
        from src.mcp_server.server import AxonMCPServer
        print("Import successful")
    except Exception as e:
        print(f"Import failed: {e}")
        import traceback
        traceback.print_exc()
