import logging
import os

import webdav
from webdav import OperationFailed
from config import Config

logger = logging.getLogger(__name__)



class WebdavManager:

    def __init__(self, config: Config):

        self.root_dir = config.get_webdav_root_dir

        self.webdav_client = webdav.connect(
            host=config.get_webdav_host,
            username=config.get_webdav_user,
            password=config.get_webdav_password,
            protocol=config.get_webdav_protocol,
            port=config.get_webdav_port,
        )

    def upload_file(self, local_path_or_fileobj, remote_path, safe=False) -> str:
        # 留个代办，需要手动创建文件目录
        remote_path = os.path.join(self.root_dir, remote_path)
        if safe and self.webdav_client.exists(remote_path):
            logger.info(f'File {remote_path} already exists')
            return str(remote_path)
        self.webdav_client.upload(local_path_or_fileobj, remote_path)
        logger.info(f'File {remote_path} uploaded')
        return str(remote_path)

    def ls(self, dir_path: str):
        return self.webdav_client.ls(dir_path)






if __name__ == "__main__":
    config = Config()
    webdav_manager = WebdavManager(config=config)

    # 列出目录内容
    files = webdav_manager.ls('/')
    for file in files:
        print(f"Name: {file.name}, Type: {'Directory' if file.name.endswith('/') else 'File'}, Size: {file.size}")