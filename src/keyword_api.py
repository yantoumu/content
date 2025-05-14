#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词API交互模块
处理与关键词API的交互
"""

import json
import logging
import random
import time
from typing import Dict, List, Any

import requests

from src.config import config

# 配置日志
logger = logging.getLogger('content_watcher.keyword_api')

class KeywordAPI:
    """处理与关键词API的交互"""

    def __init__(self):
        """初始化API交互器"""
        self.api_url = config.keywords_api_url

        # 创建一个会话对象，用于复用连接
        self.session = requests.Session()

    def get_keyword_info(self, keywords: str, max_retries: int = 2) -> Dict[str, Any]:
        """调用API获取关键词的相关信息

        Args:
            keywords: 从URL提取的关键词，可以是单个关键词或逗号分隔的多个关键词
            max_retries: 最大重试次数，默认为2次

        Returns:
            包含API返回信息的字典，如果调用失败则返回空字典
        """
        if not keywords or not self.api_url:
            return {}

        # 重试计数器
        retry_count = 0

        # 重试循环
        while retry_count <= max_retries:
            try:
                # 构建API请求URL
                # 直接使用原始URL并附加关键词
                api_request_url = f"{self.api_url}{keywords}"

                # 添加重试信息到日志
                retry_suffix = f" (重试 {retry_count}/{max_retries})" if retry_count > 0 else ""
                # 不输出完整URL，避免敏感信息泄露
                domain_part = self.api_url.split('/')[2] if '/' in self.api_url else '***'
                keywords_count = len(keywords.split(','))
                logger.debug(f"请求关键词API，域名: {domain_part}, 关键词数量: {keywords_count}{retry_suffix}")

                # 使用session发送请求，复用连接
                response = self.session.get(api_request_url, timeout=80)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        # 只记录API状态和结果数量，不记录完整响应内容
                        status = data.get('status', 'unknown')
                        total_results = len(data.get('data', []))
                        logger.info(f"API响应状态: {status}, 结果数量: {total_results}")
                        return data
                    except json.JSONDecodeError as json_err:
                        logger.error(f"JSON解析错误: {json_err}")
                        logger.error(f"出错的关键词: {keywords}")
                        # 不输出完整URL，避免敏感信息泄露
                        domain_part = self.api_url.split('/')[2] if '/' in self.api_url else '***'
                        logger.error(f"出错的API域名: {domain_part}")
                        # 创建一个默认的空响应
                        return {
                            'status': 'error',
                            'data': [{
                                'keyword': keywords,
                                'metrics': {
                                    'avg_monthly_searches': 0,
                                    'competition': 'LOW',
                                    'competition_index': '0',
                                    'monthly_searches': []
                                }
                            }]
                        }
                elif response.status_code in [429, 500, 502, 503, 504]:
                    # 这些状态码表示服务器繁忙或暂时不可用，可以重试
                    retry_count += 1
                    if retry_count <= max_retries:
                        # 指数退避，每次重试等待时间增加
                        wait_time = 2 ** retry_count  # 2, 4, 8...
                        logger.warning(f"API请求返回{response.status_code}，将在 {wait_time} 秒后重试")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"API请求失败，重试次数超过上限: {response.status_code}")
                        return {}
                else:
                    # 其他状态码表示请求有问题，不需要重试
                    logger.warning(f"API请求失败，状态码: {response.status_code}")
                    return {}

            except requests.exceptions.Timeout:
                # 超时异常，可以重试
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"API请求超时，将在 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error("API请求超时，重试次数超过上限")
                    return {}
            except requests.exceptions.ConnectionError:
                # 连接错误，可以重试
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"API连接错误，将在 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error("API连接错误，重试次数超过上限")
                    return {}
            except Exception as e:
                # 其他异常，记录错误并返回空结果
                logger.error(f"请求关键词API时发生异常: {e}")
                return {}

            # 如果执行到这里，说明请求成功或者失败但不需要重试
            break

        # 如果重试次数超过上限，返回空结果
        return {}

    def batch_query_keywords(self, keywords_list: List[str], max_retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """批量查询关键词信息

        Args:
            keywords_list: 关键词列表
            max_retries: 最大重试次数，默认为2次

        Returns:
            关键词数据字典，键为关键词，值为API返回的数据
        """
        if not keywords_list or not self.api_url:
            return {}

        # 对关键词列表进行去重，避免重复查询
        unique_keywords = list(set(keywords_list))
        logger.debug(f"关键词去重: 原始数量 {len(keywords_list)}, 去重后数量 {len(unique_keywords)}")

        keyword_data = {}
        batch_size = 5  # 每批次最多5个关键词

        # 使用队列来管理关键词批次，便于失败重试
        from collections import deque
        keyword_queue = deque()

        # 将关键词分批加入队列
        for i in range(0, len(unique_keywords), batch_size):
            batch = unique_keywords[i:i + batch_size]
            keyword_queue.append(batch)

        # 记录失败的关键词批次，用于最终报告
        failed_batches = []

        # 处理队列中的所有批次
        while keyword_queue:
            batch = keyword_queue.popleft()
            combined_keywords = ",".join(batch)

            # 重试计数器
            retry_count = 0
            success = False

            # 尝试查询，失败时重试
            while retry_count <= max_retries and not success:
                try:
                    # 构建API请求URL
                    # 直接使用原始URL并附加关键词
                    api_url = f"{self.api_url}{combined_keywords}"

                    # 添加重试信息到日志
                    retry_suffix = f" (重试 {retry_count}/{max_retries})" if retry_count > 0 else ""
                    logger.debug(f"请求关键词API: {api_url}{retry_suffix}")

                    # 使用session发送请求，复用连接
                    response = self.session.get(api_url, timeout=80)

                    # 处理响应
                    if response.status_code == 200:
                        try:
                            batch_data = response.json()

                            # 验证API返回格式
                            if batch_data.get('status') == 'success' and 'data' in batch_data:
                                # 直接处理API返回的数据，不需要额外过滤
                                for item in batch_data.get('data', []):
                                    keyword = item.get('keyword', '')
                                    if not keyword:
                                        continue

                                    # 标准化月份名称，确保匹配一致性
                                    if 'metrics' in item and 'monthly_searches' in item['metrics']:
                                        for month_data in item['metrics']['monthly_searches']:
                                            if 'month' in month_data:
                                                # 如果月份是字符串，转换为大写
                                                if isinstance(month_data['month'], str):
                                                    month_data['month'] = month_data['month'].upper()
                                                # 如果是整数，保持不变

                                    # 验证关键词数据结构
                                    if 'metrics' not in item:
                                        logger.warning(f"关键词数据缺少metrics字段: {keyword}")
                                        continue

                                    metrics = item.get('metrics', {})
                                    if 'monthly_searches' not in metrics:
                                        logger.warning(f"关键词数据缺少monthly_searches字段: {keyword}")
                                        continue

                                    monthly_searches = metrics.get('monthly_searches', [])
                                    if not monthly_searches:
                                        logger.warning(f"关键词数据的monthly_searches为空: {keyword}")
                                        continue

                                    # 记录关键词数据
                                    if keyword in keyword_data:
                                        # 如果关键词已存在，更新数据
                                        keyword_data[keyword].update(item)
                                        logger.debug(f"更新关键词数据: {keyword}")
                                    else:
                                        keyword_data[keyword] = item
                                        logger.debug(f"新增关键词数据: {keyword}")

                                    # 记录月度数据数量
                                    logger.info(f"成功获取关键词数据: {keyword}, 包含 {len(monthly_searches)} 个月度数据")

                                # 标记为成功
                                success = True
                            else:
                                logger.warning(f"API返回状态不是success或缺少data字段: {batch_data.get('status')}")
                                # 对于API返回格式错误，不重试，直接标记为失败
                                success = False
                                break
                        except json.JSONDecodeError as json_err:
                            logger.error(f"JSON解析错误: {json_err}")
                            logger.error(f"出错的关键词批次: {combined_keywords}")
                            logger.error(f"出错的URL: {api_url}")

                            # 为每个关键词创建默认数据
                            for kw in batch:
                                keyword_data[kw] = {
                                    'keyword': kw,
                                    'metrics': {
                                        'avg_monthly_searches': 0,
                                        'competition': 'LOW',
                                        'competition_index': '0',
                                        'monthly_searches': []
                                    }
                                }
                                logger.info(f"为关键词创建默认数据: {kw}")

                            # 标记为成功，使用默认数据继续处理
                            success = True
                            break
                        except Exception as e:
                            logger.error(f"处理API响应时出错: {e}")
                            # 其他处理错误，可能是数据结构问题，不重试
                            success = False
                            break
                    elif response.status_code in [429, 500, 502, 503, 504]:
                        # 这些状态码表示服务器繁忙或暂时不可用，可以重试
                        retry_count += 1
                        if retry_count <= max_retries:
                            # 指数退避，每次重试等待时间增加
                            wait_time = 2 ** retry_count  # 2, 4, 8...
                            logger.warning(f"API请求返回{response.status_code}，将在 {wait_time} 秒后重试")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"API请求失败，重试次数超过上限: {response.status_code}")
                            # 将失败的批次放入队列尾部，以便在所有其他批次处理完后再次尝试
                            keyword_queue.append(batch)
                            failed_batches.append(batch)
                            break
                    else:
                        # 其他状态码表示请求有问题，不需要重试
                        logger.error(f"API请求失败: {response.status_code}")
                        success = False
                        break

                except requests.exceptions.Timeout:
                    # 超时异常，可以重试
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(f"API请求超时，将在 {wait_time} 秒后重试")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("API请求超时，重试次数超过上限")
                        # 将失败的批次放入队列尾部
                        keyword_queue.append(batch)
                        failed_batches.append(batch)
                        break
                except requests.exceptions.ConnectionError:
                    # 连接错误，可以重试
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(f"API连接错误，将在 {wait_time} 秒后重试")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("API连接错误，重试次数超过上限")
                        # 将失败的批次放入队列尾部
                        keyword_queue.append(batch)
                        failed_batches.append(batch)
                        break
                except Exception as e:
                    # 其他异常，记录错误并标记为失败
                    logger.error(f"请求关键词API时发生异常: {e}")
                    success = False
                    break

            # 如果批次处理失败且未放入队列尾部，记录失败信息
            if not success and batch not in keyword_queue:
                logger.warning(f"批次处理失败: {combined_keywords}")
                failed_batches.append(batch)

        # 如果有失败的批次，记录总结信息
        if failed_batches:
            failed_count = sum(len(batch) for batch in failed_batches)
            logger.warning(f"共有 {len(failed_batches)} 个批次 ({failed_count} 个关键词) 查询失败")

        return keyword_data

    def close(self):
        """关闭会话连接

        在不再需要使用API交互器时调用此方法
        """
        if hasattr(self, 'session') and self.session:
            logger.debug("关闭API交互器会话")
            self.session.close()

    def __del__(self):
        """析构函数，确保在对象被垃圾回收时关闭会话"""
        self.close()

# 创建API实例
keyword_api = KeywordAPI()
