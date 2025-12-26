
import unittest
from unittest.mock import MagicMock, AsyncMock
from src.extractors.config_extractor import ConfigExtractor
from src.database.models import File

class TestConfigExtractor(unittest.TestCase):
    def setUp(self):
        self.session = AsyncMock()
        self.extractor = ConfigExtractor(self.session)

    def test_extract_json(self):
        file = File(id=1, repository_id=1, path="appsettings.json")
        content = """
        {
            "Logging": {
                "LogLevel": {
                    "Default": "Information",
                    "Microsoft": "Warning"
                }
            },
            "AllowedHosts": "*",
            "ConnectionStrings": {
                "DefaultConnection": "Server=...;Database=...;User Id=...;Password=..."
            }
        }
        """
        
        entries = self.extractor.extract_configs(file, content)
        
        self.assertTrue(len(entries) > 0)
        
        # Check flattening
        logging_default = next((e for e in entries if e.config_key == "Logging:LogLevel:Default"), None)
        self.assertIsNotNone(logging_default)
        self.assertEqual(logging_default.config_value, "Information")
        
        # Check secret masking
        conn_str = next((e for e in entries if e.config_key == "ConnectionStrings:DefaultConnection"), None)
        self.assertIsNotNone(conn_str)
        self.assertEqual(conn_str.is_secret, 1)
        self.assertEqual(conn_str.config_value, "***")

    def test_extract_xml(self):
        file = File(id=2, repository_id=1, path="web.config")
        content = """
        <configuration>
            <appSettings>
                <add key="ClientValidationEnabled" value="true" />
                <add key="UnobtrusiveJavaScriptEnabled" value="true" />
                <add key="SecretKey" value="12345" />
            </appSettings>
            <connectionStrings>
                <add name="MyDb" connectionString="Data Source=..." />
            </connectionStrings>
        </configuration>
        """
        
        entries = self.extractor.extract_configs(file, content)
        
        self.assertTrue(len(entries) > 0)
        
        # Check appSettings
        client_val = next((e for e in entries if e.config_key == "AppSettings:ClientValidationEnabled"), None)
        self.assertIsNotNone(client_val)
        self.assertEqual(client_val.config_value, "true")
        
        # Check secret in appSettings
        secret = next((e for e in entries if e.config_key == "AppSettings:SecretKey"), None)
        self.assertIsNotNone(secret)
        self.assertEqual(secret.is_secret, 1)
        self.assertEqual(secret.config_value, "***")
        
        # Check connectionStrings
        conn_str = next((e for e in entries if e.config_key == "ConnectionStrings:MyDb"), None)
        self.assertIsNotNone(conn_str)
        self.assertEqual(conn_str.is_secret, 1)
        self.assertEqual(conn_str.config_value, "***")

if __name__ == "__main__":
    unittest.main()
