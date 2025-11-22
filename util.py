import fnmatch
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Callable
from urllib.parse import urlparse, unquote, parse_qs


def get_nested_value_expr(data, expressions, default=None):
    """
    支持复杂数据结构的表达式链取值
    """
    for expr in expressions:
        try:
            result = expr(data)
            # 可以根据需要添加更多验证逻辑
            if result is not None and result != '':
                return result
        except (KeyError, TypeError, AttributeError, IndexError, ValueError):
            continue

    return default


def get_nested_value_expr_filter(data, expressions, filter_expression=None, default=None):
    """
    支持带有过滤条件的复杂数据结构表达式取值，先过滤，再取值
    :param data:
    :param expressions:
    :param filter_expression:
    :param default:
    :return:
    """
    if filter_expression is None:
        return get_nested_value_expr(data, expressions, default)
    if filter_expression(data) is False:
        return default
    return get_nested_value_expr(data, expressions, default)


class URLFileInfo:
    """URL 文件信息提取器"""

    @staticmethod
    def get_filename_from_url(url: str) -> str:
        """从 URL 中提取文件名"""
        parsed = urlparse(url)
        path = unquote(parsed.path)  # 解码 URL 编码

        # 使用 pathlib 获取文件名
        filename = Path(path).name

        # 如果没有文件名，尝试从查询参数中获取
        if not filename or filename == '/':
            # 尝试从查询参数中获取
            if 'filename=' in parsed.query:
                for param in parsed.query.split('&'):
                    if param.startswith('filename='):
                        filename = param.split('=', 1)[1]
                        break

            # 如果还是没有，使用默认名称
            if not filename or filename == '/':
                filename = 'download_file'

        return filename

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """获取文件扩展名"""
        return Path(filename).suffix.lower()

    @staticmethod
    def guess_file_type(filename: str) -> str:
        """根据文件名猜测文件类型"""
        extension = URLFileInfo.get_file_extension(filename)

        type_mapping = {
            # 图片类型
            '.jpg': 'image', '.jpeg': 'image', '.png': 'image',
            '.gif': 'image', '.bmp': 'image', '.webp': 'image',
            '.svg': 'image', '.ico': 'image', '.tiff': 'image',

            # 视频类型
            '.mp4': 'video', '.avi': 'video', '.mov': 'video',
            '.wmv': 'video', '.flv': 'video', '.webm': 'video',
            '.mkv': 'video', '.m4v': 'video',

            # 音频类型
            '.mp3': 'audio', '.wav': 'audio', '.ogg': 'audio',
            '.flac': 'audio', '.aac': 'audio', '.m4a': 'audio',

            # 文档类型
            '.pdf': 'document', '.doc': 'document', '.docx': 'document',
            '.txt': 'document', '.rtf': 'document',
            '.xls': 'document', '.xlsx': 'document', '.ppt': 'document',
            '.pptx': 'document',

            # 压缩文件
            '.zip': 'archive', '.rar': 'archive', '.7z': 'archive',
            '.tar': 'archive', '.gz': 'archive',

            # 其他
            '.exe': 'executable', '.apk': 'executable', '.dmg': 'executable',
        }

        return type_mapping.get(extension, 'unknown')

    @staticmethod
    def get_mime_type(filename: str) -> str:
        """获取 MIME 类型"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or 'application/octet-stream'

    @staticmethod
    def analyze_url(url: str) -> dict:
        """完整分析 URL 文件信息"""
        filename = URLFileInfo.get_filename_from_url(url)
        extension = URLFileInfo.get_file_extension(filename)
        file_type = URLFileInfo.guess_file_type(filename)
        mime_type = URLFileInfo.get_mime_type(filename)

        return {
            'url': url,
            'filename': filename,
            'extension': extension,
            'file_type': file_type,
            'mime_type': mime_type,
            'filename_without_ext': Path(filename).stem
        }


def extract_twitter_graphql_params(url: str) -> Dict[str, Any]:
    """
    专门用于提取Twitter GraphQL API URL参数的函数
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    result = {}

    # 解析variables参数
    if 'variables' in query_params:
        try:
            result['variables'] = json.loads(query_params['variables'][0])
        except json.JSONDecodeError as e:
            print(f"解析variables失败: {e}")
            result['variables'] = query_params['variables'][0]

    # 解析features参数
    if 'features' in query_params:
        try:
            result['features'] = json.loads(query_params['features'][0])
        except json.JSONDecodeError as e:
            print(f"解析features失败: {e}")
            result['features'] = query_params['features'][0]

    # 解析fieldToggles参数
    if 'fieldToggles' in query_params:
        try:
            result['fieldToggles'] = json.loads(query_params['fieldToggles'][0])
        except json.JSONDecodeError as e:
            print(f"解析fieldToggles失败: {e}")
            result['fieldToggles'] = query_params['fieldToggles'][0]

    # 提取endpoint信息
    path_parts = parsed.path.split('/')
    if len(path_parts) >= 5:
        result['endpoint'] = path_parts[-1]
        result['operation_name'] = path_parts[-2]

    return result


def find_files_with_filter(
        root_dir: str,
        name_pattern: list[str] = "*",
        min_size: int = 0,
        max_size: int = None,
        file_filter: Callable[[str], bool] = None
) -> List[str]:
    """
  带过滤条件的文件查找

  Args:
      root_dir: 根目录
      name_pattern: 文件名模式，支持通配符
      min_size: 最小文件大小（字节）
      max_size: 最大文件大小（字节）
      file_filter: 自定义过滤函数

  Returns:
      匹配的文件路径列表
  """
    matched_files = []

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            full_path = os.path.join(root, file)

            if not any(fnmatch.fnmatch(file, name_p) for name_p in name_pattern):
                continue

            # 检查文件名模式
            # if not fnmatch.fnmatch(file, name_pattern):
            #     continue

            # 检查文件大小
            try:
                file_size = os.path.getsize(full_path)
                if file_size < min_size:
                    continue
                if max_size and file_size > max_size:
                    continue
            except OSError:
                continue

            # 自定义过滤
            if file_filter and not file_filter(full_path):
                continue

            matched_files.append(full_path)

    return matched_files


def keep_latest_files(
        folder_path,
        keep_count=10,
        name_pattern: list[str] = "*",
        confirm_input=False,
        dry_run=False
):
    """
    保留指定数量的最新文件，删除其他较早的文件

    Args:
        folder_path (str): 文件夹路径
        keep_count (int): 要保留的文件数量，默认为10
        name_pattern (str, optional): 指定文件扩展名，如 '.txt'
        confirm_input (bool): 是否需要人工确认框
        dry_run (bool): 是否为模拟运行（只显示不实际删除）
    """

    # 检查文件夹是否存在
    if not os.path.exists(folder_path):
        print(f"错误：文件夹 '{folder_path}' 不存在")
        return

    # 获取文件夹中的所有文件
    files = []
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isfile(item_path):  # 只处理文件，不处理文件夹
            # if file_extension is None or item.lower().endswith(file_extension.lower()):
            #     files.append(item_path)
            if any(fnmatch.fnmatch(item_path, name_p) for name_p in name_pattern):
                files.append(item_path)

    if not files:
        print("文件夹中没有找到文件")
        return

    print(f"找到 {len(files)} 个文件，将保留最新的 {keep_count} 个文件")

    # 如果文件数量不超过保留数量，不需要删除
    if len(files) <= keep_count:
        print(f"文件数量 ({len(files)}) 未超过保留数量 ({keep_count})，无需删除")
        return

    # 按创建时间排序（从早到晚）
    files.sort(key=lambda x: os.path.getctime(x))

    # 计算需要删除的文件数量
    num_to_delete = len(files) - keep_count
    files_to_delete = files[:num_to_delete]  # 最早的文件
    files_to_keep = files[num_to_delete:]  # 要保留的文件

    print("\n" + "=" * 70)
    print("将要删除的文件（最早创建的）：")
    print("-" * 70)

    # 显示将要删除的文件信息
    for i, file_path in enumerate(files_to_delete):
        create_time = os.path.getctime(file_path)
        create_time_str = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M:%S')
        file_size = os.path.getsize(file_path)
        print(f"{i + 1:2d}. {create_time_str} | {file_size:8d} 字节 | {os.path.basename(file_path)}")

    print("\n将要保留的文件（最新创建的）：")
    print("-" * 70)

    # 显示将要保留的文件信息
    for i, file_path in enumerate(files_to_keep):
        create_time = os.path.getctime(file_path)
        create_time_str = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M:%S')
        file_size = os.path.getsize(file_path)
        print(f"{i + 1:2d}. {create_time_str} | {file_size:8d} 字节 | {os.path.basename(file_path)}")

    # 如果是模拟运行，不实际删除
    if dry_run:
        print(f"\n[模拟运行] 将删除 {num_to_delete} 个文件，保留 {keep_count} 个文件")
        return

    # 确认删除
    if confirm_input:
        confirm = input(f"\n确定要删除 {num_to_delete} 个文件，保留最新的 {keep_count} 个文件吗？(y/N): ")
        if confirm.lower() != 'y':
            print("操作已取消")
            return

    # 执行删除
    deleted_count = 0
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            print(f"已删除: {os.path.basename(file_path)}")
            deleted_count += 1
        except Exception as e:
            print(f"删除失败 {os.path.basename(file_path)}: {e}")

    print(f"\n成功删除 {deleted_count} 个文件，保留了 {keep_count} 个最新文件")
