#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网站地图API交互模块
处理与网站地图API的交互
"""

import logging
import datetime
import gzip
import json
from typing import Dict, List, Any
from urllib.parse import urlparse

import requests

from src.config import config

# 配置日志
logger = logging.getLogger('content_watcher.sitemap_api')

class SitemapAPI:
    """处理与网站地图API的交互"""

    def __init__(self):
        """初始化API交互器"""
        # 使用配置中的批量提交API URL
        if config.sitemap_batch_api_url:
            # 批量提交URL - 使用正确的批量提交路径
            self.batch_api_url = config.sitemap_batch_api_url
            logger.info("批量提交API已配置")

            # 检查并警告如果路径不正确
            if not self.batch_api_url.endswith('/api/v1/sitemap-updates/batch'):
                logger.warning(f"批量提交URL路径可能不正确，应该以/api/v1/sitemap-updates/batch结尾")
        else:
            self.batch_api_url = ""
        self.api_key = config.sitemap_api_key
        self.enabled = config.sitemap_api_enabled

        # 批量提交的最大记录数
        self.max_batch_size = 20  # 根据要求设置为20条

        # 是否使用gzip压缩
        self.use_gzip = True  # 默认启用gzip压缩

    @staticmethod
    def _compress_json_data(data: Dict[str, Any]) -> bytes:
        """使用gzip压缩JSON数据

        Args:
            data: 要压缩的JSON数据

        Returns:
            压缩后的二进制数据
        """
        # 将数据转换为JSON字符串，使用更高效的编码
        json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

        # 使用gzip压缩，设置更高的压缩级别
        compressed_data = gzip.compress(json_str, compresslevel=9)

        logger.debug(f"数据压缩: 原始大小 {len(json_str)} 字节, 压缩后 {len(compressed_data)} 字节, 压缩率 {len(compressed_data)/len(json_str):.2f}")

        return compressed_data

    @staticmethod
    def _handle_response(response, operation_name="API请求"):
        """处理API响应

        Args:
            response: 请求响应对象
            operation_name: 操作名称，用于日志记录

        Returns:
            (bool, str): 是否成功和状态消息
        """
        logger.debug(f"{operation_name}响应状态码: {response.status_code}")
        logger.debug(f"{operation_name}响应头: {dict(response.headers)}")

        if response.status_code == 200:
            # 只在调试级别输出成功日志
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"{operation_name}成功: {response.status_code}")
            try:
                resp_data = response.json()
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"API响应数据: {resp_data}")
                return True, "success"
            except ValueError:
                logger.warning(f"API响应不是JSON格式: {response.text[:500]}...")
                # 如果不是JSON格式但状态码是200，仍然认为成功
                return True, "success"
        elif response.status_code in [429, 500, 502, 503, 504]:
            # 这些状态码表示服务器繁忙或暂时不可用，可以重试
            logger.warning(f"{operation_name}失败: 状态码 {response.status_code}，将重试")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = response.request.url.split('/')[2] if '/' in response.request.url else '***'
            logger.warning(f"{operation_name}请求域名: {domain_part}")
            # 移除可能包含敏感信息的请求头
            safe_headers = {k: '***' if k.lower() in ['x-api-key', 'authorization'] else v
                          for k, v in dict(response.request.headers).items()}
            logger.warning(f"{operation_name}请求头: {safe_headers}")

            # 尝试获取请求体
            request_body = ''
            if hasattr(response.request, 'body') and response.request.body:
                try:
                    if isinstance(response.request.body, bytes):
                        # 如果是压缩数据，尝试解压
                        import gzip
                        try:
                            decompressed = gzip.decompress(response.request.body)
                            request_body = decompressed.decode('utf-8')[:1000] + '...' if len(decompressed) > 1000 else decompressed.decode('utf-8')
                        except:
                            request_body = str(response.request.body)[:100] + '... (压缩数据)'
                    else:
                        request_body = str(response.request.body)[:1000] + '...' if len(str(response.request.body)) > 1000 else str(response.request.body)
                except:
                    request_body = '无法解析请求体'

            logger.warning(f"{operation_name}请求体: {request_body}")
            logger.warning(f"{operation_name}响应内容: {response.text[:1000]}..." if len(response.text) > 1000 else f"{operation_name}响应内容: {response.text}")
            return False, "retry"
        else:
            # 其他状态码表示请求有问题，不需要重试
            logger.error(f"{operation_name}失败: 状态码 {response.status_code}")
            # 不输出完整URL，避免敏感信息泄露
            domain_part = response.request.url.split('/')[2] if '/' in response.request.url else '***'
            logger.error(f"{operation_name}请求域名: {domain_part}")
            # 移除可能包含敏感信息的请求头
            safe_headers = {k: '***' if k.lower() in ['x-api-key', 'authorization'] else v
                          for k, v in dict(response.request.headers).items()}
            logger.error(f"{operation_name}请求头: {safe_headers}")

            # 尝试获取请求体
            request_body = ''
            if hasattr(response.request, 'body') and response.request.body:
                try:
                    if isinstance(response.request.body, bytes):
                        # 如果是压缩数据，尝试解压
                        import gzip
                        try:
                            decompressed = gzip.decompress(response.request.body)
                            request_body = decompressed.decode('utf-8')[:1000] + '...' if len(decompressed) > 1000 else decompressed.decode('utf-8')
                        except:
                            request_body = str(response.request.body)[:100] + '... (压缩数据)'
                    else:
                        request_body = str(response.request.body)[:1000] + '...' if len(str(response.request.body)) > 1000 else str(response.request.body)
                except:
                    request_body = '无法解析请求体'

            logger.error(f"{operation_name}请求体: {request_body}")
            logger.error(f"{operation_name}响应内容: {response.text[:1000]}..." if len(response.text) > 1000 else f"{operation_name}响应内容: {response.text}")
            return False, "fail"

    @staticmethod
    def _handle_exception(e, retry_count, max_retries, operation_name="API请求"):
        """处理异常

        Args:
            e: 异常对象
            retry_count: 当前重试次数
            max_retries: 最大重试次数
            operation_name: 操作名称，用于日志记录

        Returns:
            (bool, str): 是否应该重试和状态消息
        """
        if isinstance(e, requests.exceptions.Timeout):
            # 超时异常，可以重试
            if retry_count < max_retries:
                wait_time = 2 ** retry_count
                # 提供超时详情
                timeout_details = str(e)
                if hasattr(e, 'request') and e.request:
                    timeout_details += f"\n请求URL: {e.request.url}"
                    timeout_details += f"\n超时设置: {e.request.timeout if hasattr(e.request, 'timeout') else '80秒(默认)'}"

                logger.warning(f"{operation_name}超时，将在 {wait_time} 秒后重试\n超时详情: {timeout_details}")
                return True, "timeout"
            else:
                timeout_details = str(e)
                logger.error(f"{operation_name}超时，重试次数超过上限\n超时详情: {timeout_details}")
                return False, "fail"
        elif isinstance(e, requests.exceptions.ConnectionError):
            # 连接错误，可以重试
            if retry_count < max_retries:
                wait_time = 2 ** retry_count
                # 提供更详细的错误信息
                error_details = str(e)
                if hasattr(e, 'request') and e.request:
                    error_details += f"\n请求URL: {e.request.url}"
                    if hasattr(e.request, 'body') and e.request.body:
                        body_preview = str(e.request.body)[:100] + '...' if len(str(e.request.body)) > 100 else str(e.request.body)
                        error_details += f"\n请求体: {body_preview}"

                if hasattr(e, 'response') and e.response:
                    error_details += f"\n响应状态码: {e.response.status_code}"
                    error_details += f"\n响应内容: {e.response.text[:200]}..."

                logger.warning(f"{operation_name}连接错误，将在 {wait_time} 秒后重试\n错误详情: {error_details}")
                return True, "connection_error"
            else:
                # 提供更详细的错误信息
                error_details = str(e)
                logger.error(f"{operation_name}连接错误，重试次数超过上限\n错误详情: {error_details}")
                return False, "fail"
        else:
            # 其他异常
            import traceback
            error_type = type(e).__name__
            error_message = str(e)
            error_traceback = traceback.format_exc()

            # 收集请求相关信息
            request_info = ""
            if hasattr(e, 'request') and e.request:
                # 不输出完整URL，避免敏感信息泄露
                domain_part = e.request.url.split('/')[2] if '/' in e.request.url else '***'
                request_info += f"\n请求域名: {domain_part}"
                request_info += f"\n请求方法: {e.request.method if hasattr(e.request, 'method') else 'POST(默认)'}"
                if hasattr(e.request, 'headers') and e.request.headers:
                    # 移除可能包含敏感信息的请求头
                    safe_headers = {k: '***' if k.lower() in ['x-api-key', 'authorization'] else v
                                  for k, v in dict(e.request.headers).items()}
                    request_info += f"\n请求头: {safe_headers}"

            logger.error(f"{operation_name}时出错: [{error_type}] {error_message}{request_info}")
            logger.error(f"异常调用堆栈:\n{error_traceback}")

            # 其他异常也尝试重试
            if retry_count < max_retries:
                wait_time = 2 ** retry_count
                logger.warning(f"{operation_name}出现异常 [{error_type}]，将在 {wait_time} 秒后重试")
                return True, "other_exception"
            else:
                logger.error(f"{operation_name}异常重试次数超过上限: [{error_type}] {error_message}")
                return False, "fail"

    @staticmethod
    def _execute_with_retry(request_func, max_retries, operation_name):
        """使用重试机制执行请求

        Args:
            request_func: 请求函数，接受retry_count参数并返回响应对象
            max_retries: 最大重试次数
            operation_name: 操作名称，用于日志记录

        Returns:
            bool: 是否成功
        """
        import time
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # 执行请求函数
                response = request_func(retry_count)

                # 处理响应
                success, status = SitemapAPI._handle_response(response, operation_name)
                if success:
                    return True
                elif status == "retry":
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(f"{operation_name}返回{response.status_code}，将在 {wait_time} 秒后重试")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"{operation_name}失败，重试次数超过上限: {response.status_code}")
                        return False
                else:
                    return False

            except Exception as e:
                # 处理异常
                should_retry, _ = SitemapAPI._handle_exception(e, retry_count, max_retries, operation_name)
                if should_retry:
                    retry_count += 1
                    wait_time = 2 ** retry_count
                    time.sleep(wait_time)
                    continue
                else:
                    return False

        # 如果所有重试都失败，返回失败
        return False

    # 已移除单条提交方法，只使用批量提交

    def send_batch_updates(self, updates_data: List[Dict[str, Any]], max_retries: int = 2) -> bool:
        """批量提交多条更新数据到网站地图API

        Args:
            updates_data: 更新数据列表，每个元素包含单条提交的完整数据
            max_retries: 最大重试次数，默认为2次

        Returns:
            是否成功提交
        """
        # 记录详细的批量提交信息
        logger.debug(f"批量提交详情: 数据项数量={len(updates_data)}")
        if updates_data:
            # 只输出数据结构信息，不输出具体内容
            first_item = updates_data[0]
            trends_data = first_item.get('keyword_trends_data', [])
            logger.debug(f"第一项数据结构: 包含关键词数量={len(first_item.get('keywords', []))}, 趋势数据项数={len(trends_data)}")
        if not self.enabled:
            logger.debug("网站地图API未启用，跳过批量提交")
            return False

        if not updates_data:
            logger.warning("没有数据需要提交")
            return False

        # 检查批量提交URL是否有效
        if not self.batch_api_url:
            logger.error("批量提交URL无效")
            return False

        # 过滤掉没有有效关键词的数据
        valid_updates = []
        for update in updates_data:
            keywords = update.get('keywords', [])
            if keywords and keywords[0] and keywords[0] != "无关键词":
                valid_updates.append(update)
            else:
                # 不输出跳过URL的日志，减少日志输出
                pass

        # 更新数据列表，只保留有效关键词的数据
        updates_data = valid_updates
        logger.info(f"过滤后的有效数据数量: {len(updates_data)}")

        # 如果没有有效数据，直接返回
        if not updates_data:
            logger.warning("没有有效的数据需要提交")
            return False

        # 验证数据量不超过最大批量大小
        if len(updates_data) > self.max_batch_size:
            logger.warning(f"数据量({len(updates_data)})超过最大批量大小({self.max_batch_size})，将被截断")
            updates_data = updates_data[:self.max_batch_size]

        # 验证每条数据是否包含关键词趋势数据（现在是必需的）
        for i, update in enumerate(updates_data):
            if 'keyword_trends_data' not in update or not update.get('keyword_trends_data'):
                logger.error(f"批量提交中第{i+1}条数据缺少关键词趋势数据，无法提交")
                return False

        # 准备请求数据
        payload = {
            "updates": updates_data
        }

        # 准备请求头
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "Accept-Encoding": "gzip"  # 支持接收压缩响应
        }

        # 定义请求函数
        def make_request(retry_count):
            retry_suffix = f" (重试 {retry_count}/{max_retries})" if retry_count > 0 else ""
            # 只在第一次提交或重试时输出信息级别日志
            if retry_count == 0:
                logger.info(f"正在批量提交 {len(updates_data)} 条更新数据到API")
            else:
                logger.info(f"重试批量提交 {len(updates_data)} 条数据{retry_suffix}")

            # 检查URL是否正确
            if not self.batch_api_url.endswith('/api/v1/sitemap-updates/batch'):
                logger.warning("警告: 批量提交URL路径不正确，应该以/api/v1/sitemap-updates/batch结尾")
                # 尝试修正URL
                if '/api/v1/sitemap-updates' in self.batch_api_url and not self.batch_api_url.endswith('/batch'):
                    self.batch_api_url = f"{self.batch_api_url}/batch"
                    logger.info("已修正批量提交URL路径")
            # 不输出完整请求头，避免敏感信息泄露
            safe_headers = {k: '***' if k.lower() in ['x-api-key', 'authorization'] else v for k, v in headers.items()}
            logger.debug(f"批量提交请求头: {safe_headers}")

            if self.use_gzip:
                # 使用gzip压缩数据
                compressed_data = self._compress_json_data(payload)
                headers["Content-Encoding"] = "gzip"  # 指定发送的是压缩数据
                logger.debug(f"批量提交使用gzip压缩，压缩前大小: {len(json.dumps(payload))}, 压缩后大小: {len(compressed_data)}")

                response = requests.post(
                    self.batch_api_url,
                    headers=headers,
                    data=compressed_data,  # 使用压缩后的数据
                    timeout=80  # 增加超时时间，因为批量提交可能需要更长时间
                )
            else:
                # 不使用压缩
                logger.debug(f"批量提交不使用压缩，数据大小: {len(json.dumps(payload))}")
                response = requests.post(
                    self.batch_api_url,
                    headers=headers,
                    json=payload,
                    timeout=80  # 增加超时时间，因为批量提交可能需要更长时间
                )

            # 记录响应状态和内容
            logger.debug(f"批量提交响应状态码: {response.status_code}")
            if response.status_code != 200:
                logger.debug(f"批量提交响应内容: {response.text[:500]}...")

            return response

        # 使用重试机制执行请求
        return self._execute_with_retry(make_request, max_retries, "批量提交")

    @staticmethod
    def prepare_update_data(url: str, keywords: List[str], keyword_data: Dict[str, Any]) -> Dict[str, Any]:
        """准备单条更新数据

        Args:
            url: 新增或更新的URL
            keywords: 与URL相关的关键词列表
            keyword_data: 关键词的详细数据

        Returns:
            格式化后的更新数据
        """
        # 只在出错时记录详细信息，但不输出完整URL
        if not keyword_data or 'data' not in keyword_data or not keyword_data.get('data'):
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.debug(f"prepare_update_data 输入参数: 域名={domain_part}, 关键词数量={len(keywords) if keywords else 0}")
            logger.debug(f"keyword_data 类型: {type(keyword_data)}, 是否为空: {not bool(keyword_data)}")
            if keyword_data:
                logger.debug(f"keyword_data 键: {list(keyword_data.keys())}")
        # 解析URL获取网站首页URL
        parsed_url = urlparse(url)
        homepage_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # 准备当前时间，格式为RFC3339
        update_time = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

        # 准备基本数据
        update_data = {
            "homepage_url": homepage_url,
            "new_url": url,
            "keywords": keywords if keywords and keywords[0] else ["无关键词"],  # 如果没有有效关键词，使用“无关键词”代替
            "update_time": update_time
        }

        # 只在出错时记录关键词信息，但不输出完整URL
        if not keywords or not keywords[0]:
            domain_part = urlparse(url).netloc if url else '***'
            logger.debug(f"处理域名: {domain_part}, 关键词: {update_data['keywords']}")

        # 关键词趋势数据现在是必需的
        keyword_trends_data = []

        # 检查关键词数据是否有效
        has_valid_data = False

        # 检查关键词数据是否存在并包含数据项
        if keyword_data and 'data' in keyword_data and keyword_data['data']:
            # 检查数据项是否包含关键词和指标
            for item in keyword_data['data']:
                if 'keyword' in item and 'metrics' in item:
                    metrics = item.get('metrics', {})
                    if 'monthly_searches' in metrics and metrics['monthly_searches']:
                        has_valid_data = True
                        break

        if not has_valid_data:
            # 不输出完整URL，避免敏感信息泄露
            domain_part = urlparse(url).netloc if url else '***'
            logger.warning(f"缺少有效的关键词数据，将为域名 {domain_part} 创建包含零值的关键词趋势数据")
            # 仅记录关键词数据的结构信息，不记录完整内容
            if keyword_data:
                logger.debug(f"关键词数据结构: 类型={type(keyword_data)}, 键={list(keyword_data.keys()) if isinstance(keyword_data, dict) else 'not a dict'}")
            # 创建一个包含零值的关键词趋势数据，使用URL中提取的关键词
            if keywords and keywords[0]:
                default_keyword = keywords[0]
                current_year = datetime.datetime.now().year
                current_month = datetime.datetime.now().month

                # 创建一个包含零值的关键词趋势数据
                keyword_trends_data.append({
                    "keyword": default_keyword,
                    "metrics": {
                        "avg_monthly_searches": 0,  # 使用零值而不是伪造数据
                        "competition": "LOW",
                        "competition_index": "0",
                        "monthly_searches": [
                            {"year": str(current_year), "month": str(current_month), "searches": 0}  # 使用'searches'而不是'count'，year和month必须是字符串
                        ]
                    }
                })
        else:
            # 只处理当前查询的关键词数据
            for item in keyword_data.get('data', []):
                keyword = item.get('keyword', '')
                metrics = item.get('metrics', {})

                # 只处理当前查询的关键词（不区分大小写）
                if not keyword:
                    continue

                # 不区分大小写的关键词匹配
                keyword_lower = keyword.lower()
                keywords_lower = [k.lower() for k in keywords if k]

                if keyword_lower not in keywords_lower:
                    continue

                # 将API格式转换为目标API格式
                monthly_searches = []
                monthly_data = metrics.get('monthly_searches', [])

                for month_data in monthly_data:
                    # 将月份名称转换为数字
                    month_map = {
                        'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4,
                        'MAY': 5, 'JUNE': 6, 'JULY': 7, 'AUGUST': 8,
                        'SEPTEMBER': 9, 'OCTOBER': 10, 'NOVEMBER': 11, 'DECEMBER': 12
                    }

                    # 处理月份数据，可能是字符串或整数
                    month_value = month_data.get('month', '')
                    if isinstance(month_value, str):
                        # 如果是字符串，转换为大写并查表
                        month_name = month_value.upper()
                        month_num = month_map.get(month_name, 1)  # 默认为1月
                    elif isinstance(month_value, int):
                        # 如果已经是整数，直接使用，确保在有效范围内
                        month_num = max(1, min(12, month_value))  # 限制在 1-12 之间
                    else:
                        # 其他情况使用默认值
                        month_num = 1

                    # 获取搜索量，可能是'searches'或'count'字段
                    search_count = 0
                    if 'searches' in month_data:
                        search_count = month_data.get('searches', 0)
                    elif 'count' in month_data:
                        search_count = month_data.get('count', 0)

                    # 记录原始数据和处理后的数据，帮助调试
                    if search_count > 0:
                        logger.debug(f"关键词 {keyword} 的月度数据: 年={month_data.get('year')}, 月={month_value}, 搜索量={search_count}")

                    # 使用正确的字段名称，与目标API匹配
                    monthly_searches.append({
                        "year": str(month_data.get('year', datetime.datetime.now().year)),
                        "month": str(month_num),
                        "searches": search_count  # 使用'searches'而不是'count'，year和month必须是字符串
                    })

                # 添加关键词数据
                keyword_trends_data.append({
                    "keyword": keyword,
                    "metrics": {
                        "avg_monthly_searches": metrics.get('avg_monthly_searches', 0),
                        "competition": metrics.get('competition', 'LOW'),
                        "competition_index": str(metrics.get('competition_index', '0')),
                        "monthly_searches": monthly_searches
                    }
                })

        # 关键词趋势数据现在是必需的
        # 始终添加关键词趋势数据字段，即使是空数组
        update_data["keyword_trends_data"] = keyword_trends_data

        # 如果关键词趋势数据为空，记录警告
        if not keyword_trends_data:
            logger.warning(f"无法为URL生成有效的关键词趋势数据: {url}")

        return update_data

# 创建全局API交互器实例
sitemap_api = SitemapAPI()
