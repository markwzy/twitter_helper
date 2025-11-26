import json
import logging
from typing import Tuple, Dict, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from DrissionPage import Chromium, ChromiumOptions

from config import Config
from twitter_entitys import TwitterMedia
from util import get_nested_value_expr, get_nested_value_expr_filter

logger = logging.getLogger(__name__)

def create_twitter_browser():
    co = ChromiumOptions()
    config = Config()
    (co
     .set_user_data_path(config.get_chrom_dir)
     # .no_imgs(True) # 不显示图片
     # .mute(True) # 静音
     .set_pref('credentials_enable_service', False)  # 阻止“自动保存密码”的提示气泡
     .set_argument('--hide-crash-restore-bubble')  # 阻止“要恢复页面吗？Chrome未正确关闭”的提示气泡
     )
    return Chromium(addr_or_opts=co)


def parse_twitter_media_entity(body) -> Tuple[list[TwitterMedia], str]:
    # data = packet.response.body['data']
    data = body['data']
    entries_ex = [
        lambda d: d['user']['result']['timeline']['timeline']['instructions'][0]['entries']
    ]
    entries = get_nested_value_expr(data, entries_ex)

    if not entries or len(entries) == 0:
        logger.info('No twitter media entries found')

    result = []
    cursor = ''  # 末端游标
    if len(entries) > 0:
        for entry in entries:
            # 判断是否是游标
            cursor_type_ex = [
                lambda d: d['content']['cursorType']
            ]
            cursor_type = get_nested_value_expr_filter(entry, cursor_type_ex)
            if isinstance(cursor, str) and 'Top' == cursor_type:  # 移除Top指针
                continue
            if isinstance(cursor, str) and 'Bottom' == cursor_type:  # 移除Bottom指针
                cursor_ex = [
                    lambda d: d['content']['value']
                ]
                cursor = get_nested_value_expr_filter(entry, cursor_ex)
                continue

            full_text_ex = [
                lambda d: d['content']['itemContent']['tweet_results']['result']['legacy']['full_text']
            ]

            full_text = get_nested_value_expr_filter(entry, full_text_ex)

            post_video_description_ex = [
                lambda d: d['content']['itemContent']['tweet_results']['result']['post_video_description']]
            post_video_description = get_nested_value_expr_filter(entry, post_video_description_ex)  # 获取视频描述信息
            medias_ex = [
                lambda d: d['content']['itemContent']['tweet_results']['result']['legacy']['entities']['media'],
                lambda d: d['content']['itemContent']['tweet_results']['result']['tweet']['legacy']['entities']['media']
            ]
            medias_filter_ex = lambda d: 'itemContent' in d['content']
            medias = get_nested_value_expr_filter(entry, medias_ex, medias_filter_ex)

            card_ex = [
                lambda d:
                d['content']['itemContent']['tweet_results']['result']['card']['legacy']['binding_values'][0]['value'][
                    'string_value']
            ]
            card_string_value = get_nested_value_expr_filter(entry, card_ex)
            if card_string_value:
                card_json = json.loads(card_string_value)
                if 'video_website' == card_json.get('type'):
                    media_entities = card_json.get('media_entities')
                    for key in media_entities:
                        twitter_media = TwitterMedia()
                        twitter_media.full_text = full_text
                        media_entity = media_entities[key]
                        me_id_str = media_entity['id_str']
                        twitter_media.id_str = me_id_str
                        me_media_url_https = media_entity['media_url_https']
                        twitter_media.image_url = me_media_url_https
                        me_type = media_entity['type']
                        twitter_media.type = me_type
                        me_video_info = media_entity['video_info']
                        me_variants = me_video_info['variants']
                        if me_variants and len(me_variants) > 0:
                            max_bitrate = 0
                            for variant in me_variants:
                                if 'bitrate' in variant:
                                    bitrate = variant['bitrate']
                                    if bitrate > max_bitrate:
                                        max_bitrate = bitrate
                                        twitter_media.url = variant['url']
                        result.append(twitter_media)

            if not medias or len(medias) == 0:
                logger.info('No twitter medias entity found')

            if medias is not None and len(medias) > 0:
                for media in medias:
                    twitter_media = TwitterMedia()
                    twitter_media.full_text = full_text
                    twitter_media.description = post_video_description
                    id_str = get_nested_value_expr_filter(media, [lambda d: d['id_str']])  # 视频id
                    twitter_media.id_str = id_str
                    media_url_https = get_nested_value_expr_filter(media,
                                                                   [lambda d: d['media_url_https']])  # 缩略图
                    twitter_media.image_url = media_url_https
                    tw_type = get_nested_value_expr_filter(media, [lambda d: d['type']])  # 类型
                    twitter_media.type = tw_type
                    expanded_url = get_nested_value_expr_filter(media, [lambda d: d['expanded_url']])  # 媒体详情页
                    twitter_media.expanded_url = expanded_url
                    variants_ex = [lambda d: d['video_info']['variants']]
                    variants = get_nested_value_expr(media, variants_ex)

                    filter_tw_type = ['photo']
                    if tw_type not in filter_tw_type:
                        if not variants or len(variants) == 0:
                            logger.info('No twitter media variants found')

                    if variants is not None and len(variants) > 0:
                        max_bitrate = 0
                        for variant in variants:

                            if 'bitrate' in variant:
                                bitrate = variant['bitrate']
                                if bitrate > max_bitrate:
                                    max_bitrate = bitrate
                                    twitter_media.url = variant['url']
                    result.append(twitter_media)
    if len(result) == 0:
        logger.info(f'size is 0 cursor: {cursor}')
    if len(result) < 20:
        logger.info(f'size < 20 size is {len(result)} cursor: {cursor}')
    if len(result) > 20:
        logger.info(f'size > 20 size is {len(result)} cursor: {cursor}')
    return result, cursor


class TwitterPageSpider:

    def __init__(self):
        self.config = Config()
        self.browser = create_twitter_browser()
        self.tab = self.browser.latest_tab
        self.like_cursor = ''  # 喜欢的游标
        self.like_uri = ''
        self.like_headers = {}
        self.browser_mode = 'd'
        self.browser_shutdown = False

    def _build_req_headers(self):
        """
        构建request的请求头
        :return:
        """
        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'authorization': self.like_headers.get('authorization'),
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': self.like_headers.get('referer'),
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'x-client-transaction-id': self.like_headers.get('x-client-transaction-id'),
            'x-csrf-token': self.like_headers.get('x-csrf-token'),
            'x-twitter-active-user': 'no',
            'x-twitter-auth-type': 'OAuth2Session',
            'x-twitter-client-language': 'zh-cn',
            'x-xp-forwarded-for': self.like_headers.get('x-xp-forwarded-for'),
            'Cookie': self.like_headers.get('Cookie')
        }
        return headers

    def get_page_twitter_likes(self) -> list[TwitterMedia]:
        """
        访问Twitter的我的喜欢页面
        :return:
        """
        self.tab.listen.start('Likes')
        self.tab.get(self.config.get_twitter_like_url)
        ele_display = self.config.get_twitter_ele_display
        if ele_display is None:
            self.tab.wait(10) # 如果没有可以检测的元素，就等10s
        else:
            self.tab.wait.ele_displayed(self.config.get_twitter_ele_display)

        for packet in self.tab.listen.steps(1):
            self.like_uri = packet.url
            self.like_headers = packet.request.headers
            tw_medias_search, cursor = parse_twitter_media_entity(packet.response.body)
            self.like_cursor = cursor

            return tw_medias_search
        return []

    def scroll_page_twitter_likes(self):
        """
        通过偏移量查询下一页我喜欢
        :return:
        """
        tw_url_builder = TwitterGraphQLURL(self.like_uri)
        tw_url_builder.update_variables(cursor=self.like_cursor)
        c_url = tw_url_builder.build_url()
        headers = self._build_req_headers()
        response = requests.request("GET", c_url, headers=headers, data={})
        tw_medias_search, cursor = parse_twitter_media_entity(response.json())
        self.like_cursor = cursor

        return tw_medias_search

    def quit_browser(self):
        self.browser.quit()
        self.browser_shutdown = True


class TwitterGraphQLURL:
    """Twitter GraphQL URL解析和构建工具"""

    def __init__(self, ori_url: str):
        self.original_url = ori_url
        self.parsed_url = urlparse(ori_url)
        self.params = self._parse_params()

    def _parse_params(self) -> Dict[str, Any]:
        """解析URL参数"""
        query_params = parse_qs(self.parsed_url.query)
        result = {}

        for key in ['variables', 'features', 'fieldToggles']:
            if key in query_params:
                try:
                    result[key] = json.loads(query_params[key][0])
                except json.JSONDecodeError:
                    result[key] = query_params[key][0]

        return result

    def update_variables(self, **kwargs):
        """更新variables参数"""
        if 'variables' not in self.params:
            self.params['variables'] = {}
        self.params['variables'].update(kwargs)

    def update_features(self, **kwargs):
        """更新features参数"""
        if 'features' not in self.params:
            self.params['features'] = {}
        self.params['features'].update(kwargs)

    def update_field_toggles(self, **kwargs):
        """更新fieldToggles参数"""
        if 'fieldToggles' not in self.params:
            self.params['fieldToggles'] = {}
        self.params['fieldToggles'].update(kwargs)

    def build_url(self) -> str:
        """构建新的URL"""
        query_dict = {}

        for key in ['variables', 'features', 'fieldToggles']:
            if key in self.params and self.params[key] is not None:
                query_dict[key] = json.dumps(
                    self.params[key],
                    separators=(',', ':'),
                    ensure_ascii=False
                )

        query_string = urlencode(query_dict, doseq=True)

        return urlunparse((
            self.parsed_url.scheme,
            self.parsed_url.netloc,
            self.parsed_url.path,
            self.parsed_url.params,
            query_string,
            self.parsed_url.fragment
        ))

    def __str__(self):
        return self.build_url()
