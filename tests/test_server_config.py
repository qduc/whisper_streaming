import pytest
from unittest.mock import MagicMock, patch
from whisper_online_server import ServerConfig, load_config
from translation_interfaces import TranslationConfig
import os

def create_mock_args(**kwargs):
    """Create mock arguments for testing"""
    defaults = {
        'host': 'localhost',
        'port': 8000,
        'websocket': False,
        'warmup_file': None,
        'config': 'test_config.yaml',
        'translate': False,
        'target_language': None,
        'translation_interval': None,
        'max_buffer_time': None,
        'min_text_length': None,
        'translation_model': None,
        'translation_provider': None,
        'inactivity_timeout': None,
        'backend': 'faster-whisper',
        'model': 'base',
        'lan': 'en',
    }
    defaults.update(kwargs)
    return MagicMock(**defaults)

class TestServerConfig:
    @pytest.fixture
    def yaml_config(self):
        return {
            'translation': {
                'target_language': 'vi',
                'model': 'gemini-2.0-flash',
                'provider': 'gemini',
                'interval': 3.0,
                'max_buffer_time': 10.0,
                'min_text_length': 20,
                'inactivity_timeout': 2.0,
                'system_prompt': 'Custom prompt'
            }
        }
    
    def test_basic_config(self):
        args = create_mock_args()
        config = ServerConfig(args)
        
        assert config.host == 'localhost'
        assert config.port == 8000
        assert config.websocket is False
        assert config.translation_config is None
    
    def test_translation_config_from_yaml(self, yaml_config):
        with patch('whisper_online_server.load_config', return_value=yaml_config):
            args = create_mock_args(translate=True)
            config = ServerConfig(args)
            
            assert config.translation_config is not None
            assert config.translation_config.target_language == 'vi'
            assert config.translation_config.model == 'gemini-2.0-flash'
            assert config.translation_config.provider == 'gemini'
    
    def test_cli_args_override_yaml(self, yaml_config):
        with patch('whisper_online_server.load_config', return_value=yaml_config):
            args = create_mock_args(
                translate=True,
                target_language='es',
                translation_model='gpt-4',
                translation_provider='openai'
            )
            config = ServerConfig(args)
            
            assert config.translation_config.target_language == 'es'
            assert config.translation_config.model == 'gpt-4'
            assert config.translation_config.provider == 'openai'
    
    def test_missing_config_file(self):
        args = create_mock_args(config='nonexistent.yaml')
        config = ServerConfig(args)
        
        # Should use defaults when config file is missing
        assert config.translation_config is None
    
    def test_partial_cli_overrides(self, yaml_config):
        with patch('whisper_online_server.load_config', return_value=yaml_config):
            args = create_mock_args(
                translate=True,
                target_language='es'  # Override only language
            )
            config = ServerConfig(args)
            
            assert config.translation_config.target_language == 'es'
            assert config.translation_config.model == 'gemini-2.0-flash'  # From YAML
            assert config.translation_config.provider == 'gemini'  # From YAML

class TestConfigLoading:
    def test_load_nonexistent_config(self):
        config = load_config('nonexistent.yaml')
        assert config == {'translation': {}}
    
    def test_load_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("invalid: yaml: content")
        
        config = load_config(str(config_file))
        assert config == {'translation': {}}
    
    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
translation:
    target_language: vi
    model: gemini-2.0-flash
    provider: gemini
""")
        
        config = load_config(str(config_file))
        assert config['translation']['target_language'] == 'vi'
        assert config['translation']['model'] == 'gemini-2.0-flash'
        assert config['translation']['provider'] == 'gemini'