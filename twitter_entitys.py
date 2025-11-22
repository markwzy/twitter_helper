import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Tuple


@dataclass
class User:
    id: int
    name: str
    email: str
    age: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True


@dataclass
class TwitterMedia:
    id: Optional[int] = None
    id_str: str = ""
    type: Optional[str] = None
    process_status: Optional[str] = 'init'  # 状态，init：初始化；done：终态完成；processing：处理中；fail：处理失败
    expanded_url: Optional[str] = None  # 媒体详情页

    full_text: Optional[str] = None  # 博文文本内容

    description: Optional[str] = None  # 视频描述
    description_zh: Optional[str] = None  # 翻译之后的视频描述

    image_url: Optional[str] = None  # 视频封面
    oss_image_path: Optional[str] = None  # 视频封面存储地址

    url: Optional[str] = None  # 视频连接
    oss_url_path: Optional[str] = None  # 视频存储地址

    file_size: Optional[int] = None  # 文件大小
    elapsed_time: Optional[float] = None  # 下载时间

    profile_image_url: Optional[str] = None
    profile_image_url_zh: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        result = asdict(self)
        if isinstance(self.created_at, datetime):
            result['created_at'] = self.created_at.isoformat()
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def find_media_difference_dict(list1: list[TwitterMedia], list2: list[TwitterMedia]) -> Tuple[
    list[TwitterMedia], list[TwitterMedia]]:
    # 将第二个列表转换为字典，key 为 id_str
    dict2 = {media.id_str: media for media in list2}

    only_in_list1 = []
    for media in list1:
        if media.id_str not in dict2:
            only_in_list1.append(media)

    # 同样处理第二个列表
    dict1 = {media.id_str: media for media in list1}
    only_in_list2 = [media for media in list2 if media.id_str not in dict1]

    return only_in_list1, only_in_list2
