import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """下载结果类"""
    id: str
    url: str
    save_path: str
    success: bool
    file_size: int = 0
    error: Optional[str] = None
    elapsed_time: float = 0.0


class AsyncDownloader:
    """异步下载器类"""

    def __init__(self, max_concurrent: int = 5, timeout: int = 30, chunk_size: int = 8192):
        """
        初始化下载器

        Args:
            max_concurrent: 最大并发下载数
            timeout: 请求超时时间（秒）
            chunk_size: 分块大小
        """
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.chunk_size = chunk_size
        self.results: List[DownloadResult] = []

    async def _download_single(self, session: aiohttp.ClientSession, id_str: str, url: str, save_path: str) -> DownloadResult:
        """下载单个文件"""
        start_time = time.time()

        if os.path.exists(save_path):
            return DownloadResult(
                    id=id_str,
                    url=url,
                    save_path=save_path,
                    success=True,
                )

        try:
            async with session.get(url) as response:
                response.raise_for_status()

                save_path_obj = Path(save_path)
                original_name = save_path_obj.name

                downloading_name = original_name + '.downloading'

                dir_name = os.path.dirname(save_path)

                downloading_save_path = os.path.join(dir_name, downloading_name)

                # 创建保存目录
                os.makedirs(os.path.dirname(downloading_save_path), exist_ok=True)

                # 获取文件大小（如果服务器提供）
                file_size = 0
                with open(downloading_save_path, 'wb') as file:
                    async for chunk in response.content.iter_chunked(self.chunk_size):
                        file.write(chunk)
                        file_size += len(chunk)

                os.rename(downloading_save_path, save_path)
                elapsed_time = time.time() - start_time
                logger.info(f"下载完成: {save_path} ({file_size} bytes, 耗时: {elapsed_time:.2f}s)")

                return DownloadResult(
                    id=id_str,
                    url=url,
                    save_path=save_path,
                    success=True,
                    file_size=file_size,
                    elapsed_time=elapsed_time
                )

        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"下载失败 {url}: {str(e)}"
            logger.error(error_msg)

            # 删除可能已创建的不完整文件
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except:
                    pass

            return DownloadResult(
                id=id_str,
                url=url,
                save_path=save_path,
                success=False,
                error=error_msg,
                elapsed_time=elapsed_time
            )

    async def download(self, urls_and_paths: List[Tuple[str, str, str]],
                       headers: Optional[dict] = None) -> List[DownloadResult]:
        """
        下载多个文件

        Args:
            urls_and_paths: [(url1, save_path1), (url2, save_path2), ...]
            headers: 自定义请求头

        Returns:
            下载结果列表
        """
        if headers is None:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
            }

        # 创建连接器限制并发数
        connector = aiohttp.TCPConnector(limit=self.max_concurrent)

        async with aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
                headers=headers
        ) as session:

            tasks = []
            for id_str, url, save_path in urls_and_paths:
                task = self._download_single(session, id_str, url, save_path)
                tasks.append(task)

            self.results = await asyncio.gather(*tasks)
            return self.results

    def get_statistics(self) -> dict:
        """获取下载统计信息"""
        if not self.results:
            return {}

        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]

        total_size = sum(r.file_size for r in successful)
        total_time = sum(r.elapsed_time for r in self.results)

        return {
            'total_tasks': len(self.results),
            'successful': len(successful),
            'failed': len(failed),
            'success_rate': len(successful) / len(self.results),
            'total_size': total_size,
            'average_speed': total_size / total_time if total_time > 0 else 0,
            'total_time': total_time
        }

    def print_summary(self):
        """打印下载摘要"""
        stats = self.get_statistics()

        if not stats:
            print("没有下载任务")
            return

        logger.info("\n" + "=" * 50)
        logger.info("下载摘要")
        logger.info("=" * 50)
        logger.info(f"总任务数: {stats['total_tasks']}")
        logger.info(f"成功: {stats['successful']}")
        logger.info(f"失败: {stats['failed']}")
        logger.info(f"成功率: {stats['success_rate']:.1%}")
        logger.info(f"总大小: {stats['total_size'] / 1024 / 1024:.2f} MB")
        logger.info(f"平均速度: {stats['average_speed'] / 1024:.2f} KB/s")
        logger.info(f"总耗时: {stats['total_time']:.2f} 秒")

        # 打印失败的任务
        failed_tasks = [r for r in self.results if not r.success]
        if failed_tasks:
            logger.error("\n失败任务:")
            for result in failed_tasks:
                logger.error(f"  - {result.url} -> {result.error}")


# 使用示例
async def main():
    # 创建下载器实例
    downloader = AsyncDownloader(max_concurrent=3, timeout=60)

    # 准备下载任务
    download_tasks = [
        ("123","https://video.twimg.com/amplify_video/1987945021430001664/vid/avc1/720x720/0oHbn-exo00ea-nx.mp4?tag=21", "mov/0oHbn-exo00ea-nx.mp4"),
    ]

    # 执行下载
    logger.info("开始下载...")
    results = await downloader.download(download_tasks)

    # 打印统计信息
    downloader.print_summary()


# 更简洁的使用方式
async def simple_example():
    """简化使用示例"""
    downloader = AsyncDownloader()

    tasks = [
        ("123", "https://example.com/file1.zip", "downloads/file1.zip"),
        ("456", "https://example.com/file2.zip", "downloads/file2.zip"),
    ]

    await downloader.download(tasks)
    downloader.print_summary()


# 带自定义请求头的使用示例
async def example_with_headers():
    """带自定义请求头的示例"""
    downloader = AsyncDownloader(max_concurrent=2)

    custom_headers = {
        'User-Agent': 'MyDownloader/1.0',
        'Referer': 'https://example.com',
        'Authorization': 'Bearer your_token_here'  # 如果需要认证
    }

    tasks = [
        ("123", "https://api.example.com/data1", "data/file1.json"),
        ("456", "https://api.example.com/data2", "data/file2.json"),
    ]

    await downloader.download(tasks, headers=custom_headers)
    downloader.print_summary()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())