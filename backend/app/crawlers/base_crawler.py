"""
基础爬虫类
定义爬虫的通用接口和方法
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from loguru import logger


class BaseCrawler(ABC):
    """基础爬虫抽象类"""

    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """
        初始化爬虫

        Args:
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    def extract_product_id(self, url: str) -> str:
        """从 URL 提取商品 ID"""
        pass

    @abstractmethod
    def fetch_product_info(self, url: str) -> Dict[str, Any]:
        """抓取商品基础信息，如商品名、标准化链接等"""
        pass

    @abstractmethod
    def fetch_comments(self, product_id: str, page: int = 1) -> List[Dict[str, Any]]:
        """
        采集评论

        Args:
            product_id: 商品 ID
            page: 页码

        Returns:
            评论列表
        """
        pass

    @abstractmethod
    def parse_comment(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析单条评论

        Args:
            comment_data: 原始评论数据

        Returns:
            解析后的评论数据
        """
        pass

    def crawl(self, url: str, max_pages: int = 10) -> List[Dict[str, Any]]:
        """
        爬取商品评论（主流程）

        Args:
            url: 商品链接
            max_pages: 最大爬取页数

        Returns:
            评论列表
        """
        try:
            product_id = self.extract_product_id(url)
            logger.info(f"Extracted product ID: {product_id}")

            comments = []

            # max_pages 参数名为兼容旧接口保留，但在动态评论爬虫里实际表示抓取/滚动轮次。
            for round_index in range(1, max_pages + 1):
                logger.info(f"Fetching comment round {round_index}...")

                try:
                    page_comments = self.fetch_comments(product_id, round_index)

                    if not page_comments:
                        logger.info(f"No more comments at round {round_index}")
                        break

                    for comment_data in page_comments:
                        try:
                            parsed = self.parse_comment(comment_data)
                            if parsed:
                                comments.append(parsed)
                        except Exception as e:
                            logger.warning(f"Failed to parse comment: {str(e)}")
                            continue

                    logger.info(f"Round {round_index} fetched: {len(page_comments)} comments")

                except Exception as e:
                    logger.error(f"Failed to fetch round {round_index}: {str(e)}")
                    continue

            logger.info(f"Crawling completed: {len(comments)} comments fetched")
            return comments

        except Exception as e:
            logger.error(f"Crawling failed: {str(e)}")
            raise
