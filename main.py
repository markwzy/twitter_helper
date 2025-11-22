import asyncio
import logging
import os
import shutil
import threading
import time
from pathlib import Path

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from llm_translation import LLMTranslation
from twitter_entitys import TwitterMedia
from twitter_manager import TwitterManager
from twitter_page_spider import TwitterPageSpider
from util import find_files_with_filter, URLFileInfo, keep_latest_files
from webdav_manager import WebdavManager


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


class TwitterTask:
    def __init__(self):
        self.config = Config()
        self.scheduler = BackgroundScheduler()
        self.twitter_manager = TwitterManager()
        self.webdav_manager = WebdavManager(config=self.config)
        self.llm_translation = LLMTranslation()
        self.downloading = False
        self.job_lock = threading.Lock()
        self.translation_lock = threading.Lock()
        self.translating = False

    def fetch_data_from_twitter_like(self):
        """
        从Twitter获取喜欢列表数据，存储到MongoDB
        :return:
        """
        twitter_page_spider = None
        try:
            twitter_page_spider = TwitterPageSpider()
            first_load_page = True
            while True:
                if first_load_page:
                    tw_medias = twitter_page_spider.get_page_twitter_likes()
                else:
                    tw_medias = twitter_page_spider.scroll_page_twitter_likes()
                if len(tw_medias) == 0:
                    return
                first_load_page = False
                id_str_list = [twitter_media.id_str for twitter_media in tw_medias]
                tw_medias_from_db = self.twitter_manager.query_twitter_media_by_id_str_list(id_str_list)
                tw_medias_filtered = []
                tw_medias_dict = {tw_media.id_str: tw_media for tw_media in tw_medias_from_db}
                for twitter_media_from_web in tw_medias:
                    if twitter_media_from_web is not None:
                        if twitter_media_from_web.id_str not in tw_medias_dict:
                            tw_medias_filtered.append(twitter_media_from_web)
                if len(tw_medias_filtered) > 0:
                    for tw_media in tw_medias_filtered:
                        self.twitter_manager.save_twitter_media(tw_media)
                else:
                    break
        except Exception as e:
            logger.error(f'获取数据失败：{e}')
        # 关闭浏览器
        if twitter_page_spider is not None:
            twitter_page_spider.quit_browser()
        pass

    def download_media_from_twitter_like(self):
        """
        从Twitter下载视频媒体
        :return:
        """
        with self.job_lock:
            if self.downloading:
                logger.info('有正在下载的任务')
                return
            self.downloading = True
        try:
            logger.info('开始查询数据')
            tw_medias = self.twitter_manager.query_init_twitter_medias(5)
            logger.info(f'查询到了 {len(tw_medias)} 条数据，开始开启下载任务')
            asyncio.run(self.twitter_manager.download_twitter_media(tw_medias))
            logger.info(f'下载任务执行完成')
        except Exception as e:
            logger.error(f'下载任务出错：{e}')
        finally:
            with self.job_lock:
                self.downloading = False
        pass

    def upload_media_to_jkj(self):
        """
        上传到极空间
        :return:
        """
        file_path_list = find_files_with_filter(
            'twitter/download',
            name_pattern=['*.mp4', '*.jpg', '*.png'],
        )

        for file_path in file_path_list:
            file_name = Path(file_path).name
            file_name_arr = file_name.split('_')
            id_str = file_name_arr[0]
            tw_type = file_name_arr[1]

            remote_path = os.path.join('twitter/media', file_name)

            self.webdav_manager.upload_file(file_path, remote_path, safe=True)

            # 将上传的文件移动到uploaded文件夹中
            upload_file_path = os.path.join('twitter/uploaded', file_name)
            os.makedirs(os.path.dirname(upload_file_path), exist_ok=True)
            if os.path.exists(upload_file_path):
                logger.info(f'upload file {upload_file_path} already exists')
                os.remove(upload_file_path)
                continue
            shutil.move(file_path, 'twitter/uploaded')  # 待优化
            update = TwitterMedia(
                process_status='uploaded',
                id_str=id_str,
                oss_url_path=str(remote_path),
            )
            if 'photo' == tw_type or 'animated_gif' == tw_type:
                update.oss_image_path = upload_file_path
                self.twitter_manager.update_twitter_media_by_id_str(update)
            if 'video' == tw_type and URLFileInfo.get_file_extension(file_name) == '.mp4':
                self.twitter_manager.update_twitter_media_by_id_str(update)
            time.sleep(2)
        pass

    def delete_from_uploaded(self):
        """
        从本地磁盘删除
        :return:
        """
        logger.info(f'开始删除文件')
        keep_latest_files('twitter/uploaded', keep_count=0, name_pattern=['*.mp4', '*.jpg', '*.png'])
        logger.info(f'删除文件完成')
        pass

    def translation(self):
        with self.translation_lock:
            if self.translating:
                logger.info('有正在翻译的任务')
                return
            self.translating = True
        try:
            tw_media = self.twitter_manager.find_un_translation()
            if tw_media:
                logger.info(f'开始翻译{tw_media.id_str}')
                description_zh = self.llm_translation.translate(tw_media.description)
                update = TwitterMedia(
                    id_str=tw_media.id_str,
                    description_zh=description_zh,
                    process_status=tw_media.process_status,
                )
                self.twitter_manager.update_twitter_media_by_id_str(update)
                logger.info(f'结束翻译{tw_media.id_str}')
        except Exception as e:
            logger.error(f'翻译出错: {e}')
        finally:
            with self.translation_lock:
                self.translating = False

    def job_listener(self, event):
        """
        作业执行监听器
        :return:
        """
        if event.exception:
            logger.error(f'作业 {event.job_id} 执行失败：{event.exception}')
        else:
            logger.info(f'作业 {event.job_id} 执行完成')
        pass

    def setup_scheduler(self):
        """
        配置调度器
        :return:
        """
        self.scheduler.add_listener(self.job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        self.scheduler.add_job(
            self.fetch_data_from_twitter_like,
            'cron',
            hour='*/4',
            minute='0',
            id='daytime_fetch',
        )

        self.scheduler.add_job(
            self.download_media_from_twitter_like,
            'cron',
            hour='*',
            minute='*',
            id='download_media',
        )

        self.scheduler.add_job(
            self.upload_media_to_jkj,
            'cron',
            hour='*/2',
            minute='*',
            id='upload_media',
        )

        self.scheduler.add_job(
            self.delete_from_uploaded,
            'cron',
            hour='*',
            minute='*/15',
            id='delete_from_uploaded',
        )

        self.scheduler.add_job(
            self.translation,
            'interval',
            seconds=5,
            max_instances=1,
            id='translation',
        )

        pass

    def start(self):
        """
        启动调度器
        :return:
        """
        self.setup_scheduler()
        self.scheduler.start()
        logger.info("抓取任务调度器已启动")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()
            logger.info("抓取任务调度器已停止")
        pass


if __name__ == '__main__':
    logger.info('Starting twitter task')
    tw_task = TwitterTask()
    tw_task.start()
    # tw = TwitterTask()
    # tw.fetch_data_from_twitter_like()
