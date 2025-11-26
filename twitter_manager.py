import asyncio
import logging
from typing import Dict

from dacite import from_dict
from pymongo.errors import DuplicateKeyError

from download import AsyncDownloader
from mongo_manager import connect_twitter_db
from twitter_entitys import TwitterMedia
from util import URLFileInfo

logger = logging.getLogger(__name__)

class TwitterManager:

    def __init__(self):
        self.twitter_db = connect_twitter_db()
        self.twitter_media_collection = self.twitter_db.twitter_media

    def get_next_sequence(self, collection_name='twitter_media'):
        """获取下一个自增ID"""
        counter_collection = self.twitter_db.counters
        result = counter_collection.find_one_and_update(
            {"_id": collection_name},
            {"$inc": {"sequence_value": 1}},
            upsert=True,
            return_document=True
        )
        return result["sequence_value"]

    def save_twitter_media(self, tw_media: TwitterMedia):
        next_id = self.get_next_sequence('twitter_media')

        tw_media.id = next_id
        # 转换为字典
        media_dict = {
            "_id": next_id,  # 使用自增ID作为MongoDB的_id
            "id_str": tw_media.id_str,
            "type": tw_media.type,
            "process_status": tw_media.process_status,
            "expanded_url": tw_media.expanded_url,

            "full_text": tw_media.full_text,

            "description": tw_media.description,
            "description_zh": tw_media.description_zh,

            "image_url": tw_media.image_url,
            "oss_image_path": tw_media.oss_image_path,

            "url": tw_media.url,
            "oss_url_path": tw_media.oss_url_path,

            "file_size": tw_media.file_size,
            "elapsed_time": tw_media.elapsed_time,

            "profile_image_url": tw_media.profile_image_url,
            "profile_image_url_zh": tw_media.profile_image_url_zh,

            "created_at": tw_media.created_at
        }

        try:
            self.twitter_media_collection.insert_one(media_dict)
        except DuplicateKeyError as e:
            logger.error(f'duplicate key {e.details['keyValue']['id_str']}')
            return
        logger.info(f'ID为: {next_id} 插入数据库')

    def save_twitter_media_batch(self, tw_media_batch: list[TwitterMedia]):
        if tw_media_batch is None or len(tw_media_batch) == 0:
            return 0
        num = 0
        for tw_media in tw_media_batch:
            self.save_twitter_media(tw_media)
            num += 1
        return num

    def query_one_twitter_media_by_id_str(self, id_str: str) -> TwitterMedia | None:
        tw_media = self.twitter_media_collection.find_one({"id_str": id_str})
        if tw_media:
            return from_dict(data_class=TwitterMedia, data=tw_media)
        return None

    def query_twitter_media_by_id_str_list(self, id_str_list: list) -> list[TwitterMedia]:
        """
        按id_str批量查询
        :param id_str_list:
        :return:
        """
        if id_str_list is None or len(id_str_list) == 0:
            return []
        tw_media_cursor = self.twitter_media_collection.find({"id_str": {"$in": id_str_list}})
        if tw_media_cursor is not None:
            tw_medias = []
            for tw_media in tw_media_cursor:
                tw_medias.append(from_dict(data_class=TwitterMedia, data=tw_media))
            return tw_medias
        return []

    def query_init_twitter_medias(self, limit=3) -> list[TwitterMedia] | None:
        tw_media_cursor = self.twitter_media_collection.find({"process_status": 'init'}).limit(limit)
        if tw_media_cursor is not None:
            tw_medias = []
            for tw_media in tw_media_cursor:
                tw_medias.append(from_dict(data_class=TwitterMedia, data=tw_media))
            return tw_medias
        return None

    def update_twitter_media_by_id_str(self, tw_media: TwitterMedia):
        query = {"id_str": tw_media.id_str}
        update_files = {}
        if tw_media.image_url is not None:
            update_files["image_url"] = tw_media.image_url
        if tw_media.process_status is not None:
            update_files["process_status"] = tw_media.process_status
        if tw_media.oss_url_path is not None:
            update_files["oss_url_path"] = tw_media.oss_url_path
        if tw_media.description_zh is not None:
            update_files["description_zh"] = tw_media.description_zh
        if tw_media.oss_image_path is not None:
            update_files["oss_image_path"] = tw_media.oss_image_path
        if tw_media.file_size is not None:
            update_files["file_size"] = tw_media.file_size
        if tw_media.elapsed_time is not None:
            update_files["elapsed_time"] = tw_media.elapsed_time

        if update_files:
            update = {"$set": update_files}
            self.twitter_media_collection.update_one(query, update)

    async def download_twitter_media(self, twitter_medias: list[TwitterMedia]):
        if twitter_medias is None or len(twitter_medias) == 0:
            return -1

        download_tasks_photo = []  # 图片下载器任务
        download_tasks_video = []  # 视频下载器任务
        for tw_media in twitter_medias:
            tw_type = tw_media.type
            if tw_media.image_url is not None:
                download_tasks_photo.append((
                    URLFileInfo.get_filename_from_url(tw_media.image_url),
                    tw_media.image_url,
                    f"twitter/download/{tw_media.id_str}_{tw_type}_{URLFileInfo.get_filename_from_url(tw_media.image_url)}"
                ))
            if tw_media.url is not None:
                download_tasks_video.append((
                    URLFileInfo.get_filename_from_url(tw_media.url),
                    tw_media.url,
                    f"twitter/download/{tw_media.id_str}_{tw_type}_{URLFileInfo.get_filename_from_url(tw_media.url)}"
                ))

        # 创建图片下载器实例
        downloader_photo = AsyncDownloader(max_concurrent=3, timeout=3600)

        # 创建视频下载器实例
        downloader_video = AsyncDownloader(max_concurrent=3, timeout=3600)

        download_result = await asyncio.gather(
            downloader_photo.download(download_tasks_photo),
            downloader_video.download(download_tasks_video)
        )

        tw_media_dict: Dict[str, TwitterMedia] = {}
        for tw_media in twitter_medias:
            if tw_media.type is not None and (
                    'photo' == tw_media.type or 'animated_gif' == tw_media.type) and tw_media.image_url is not None:
                tw_media_dict[URLFileInfo.get_filename_from_url(tw_media.image_url)] = tw_media
            if tw_media.type is not None and 'video' == tw_media.type:
                if tw_media.url is not None:
                    tw_media_dict[URLFileInfo.get_filename_from_url(tw_media.url)] = tw_media
                if tw_media.image_url is not None:
                    tw_media_dict[URLFileInfo.get_filename_from_url(tw_media.image_url)] = tw_media

        num = 0
        if download_result is not None and len(download_result) > 0:
            for download_result_item in download_result:
                if download_result_item is not None and len(download_result_item) > 0:
                    for result_item in download_result_item:
                        tw_media = tw_media_dict.get(result_item.id)
                        if tw_media is not None and ('photo' == tw_media.type or 'animated_gif' == tw_media.type):
                            update = TwitterMedia(
                                id_str=tw_media.id_str,
                                process_status='download',
                                file_size=result_item.file_size,
                                elapsed_time=result_item.elapsed_time,
                            )
                            self.update_twitter_media_by_id_str(update)
                            num += 1

                        if tw_media is not None and 'video' == tw_media.type:
                            if result_item.url is not None and tw_media.url is not None:
                                if result_item.url == tw_media.url:
                                    update = TwitterMedia(
                                        id_str=tw_media.id_str,
                                        process_status='download',
                                        file_size=result_item.file_size,
                                        elapsed_time=result_item.elapsed_time,
                                    )
                                    self.update_twitter_media_by_id_str(update)
                                    num += 1

        return num

    def find_un_translation(self) -> TwitterMedia | None:
        query = {
            "description": {"$ne": None},
            "description_zh": {"$eq": None}
        }

        tw_media = self.twitter_media_collection.find_one(query)
        if tw_media:
            return from_dict(data_class=TwitterMedia, data=tw_media)
        return None


if __name__ == '__main__':
    manager = TwitterManager()
    media = manager.find_un_translation()
    print(media)
    # media = manager.query_one_twitter_media_by_id_str('1987360869085532160')
    # manager.save_twitter_media(media)
    # print(media.to_json())

    # twitter_entities = manager.query_twitter_media_by_id_str_list(['1987360869085532160'])
    # print(twitter_entities)

    # medias = manager.query_twitter_media_by_id_str_list(['1987821085333868544', '1987945021430001664'])
    # print(medias)
    # asyncio.run(manager.download_twitter_media(medias))
