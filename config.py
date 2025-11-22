import os
from typing import Optional

from dotenv import load_dotenv


class Config:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, env_file: Optional[str] = None):
        if env_file:
            load_dotenv(env_file)
        else:
            # 根据环境加载不同的 .env 文件
            env = os.getenv('ENVIRONMENT', 'development')
            env_file = f'.env.{env}'
            if os.path.exists(env_file):
                load_dotenv(env_file)
            else:
                load_dotenv('.env')  # 回退到默认 .env

    @property
    def get_webdav_host(self) -> str:
        return os.getenv('WEBDAV_HOST', '127.0.0.1')

    @property
    def get_webdav_port(self) -> int:
        return int(os.getenv('WEBDAV_PORT', '8080'))

    @property
    def get_webdav_user(self) -> str:
        return os.getenv('WEBDAV_USER', 'root')

    @property
    def get_webdav_password(self) -> str:
        return os.getenv('WEBDAV_PASSWORD', '<PASSWORD>')

    @property
    def get_webdav_protocol(self) -> str:
        return os.getenv('WEBDAV_PROTOCOL', 'http')

    @property
    def get_webdav_root_dir(self) -> str:
        return os.getenv('WEBDAV_ROOT_DIR', '/')

    @property
    def get_mongo_url(self) -> str:
        return os.getenv('MONGO_CONNECT_URL', 'mongodb://username:password@127.0.0.1:27017/?directConnection=true')

    @property
    def get_chrom_dir(self) -> str:
        return os.getenv('CHROME_DIR', '/')

    @property
    def get_twitter_like_url(self) -> str:
        return os.getenv('TWITTER_LIKE_URL', 'https://twitter.com/twitter')

    @property
    def get_twitter_ele_display(self) -> str:
        return os.getenv('TWITTER_ELE_DISPLAY', '')

    @property
    def get_llm_model_name(self) -> str:
        return os.getenv('LLM_MODEL_NAME', 'qwen/qwen3-vl-8b')

    @property
    def get_llm_api_base(self) -> str:
        return os.getenv('LLM_API_BASE', 'qwen/qwen3-vl-8b')

    @property
    def get_llm_api_key(self) -> str:
        return os.getenv('LLM_API_KEY', '')
