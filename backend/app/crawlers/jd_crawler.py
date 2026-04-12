"""
京东爬虫实现
使用 DrissionPage 采集京东商品评论
"""

import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from loguru import logger

try:
    from DrissionPage import ChromiumPage
except ImportError:
    logger.warning("DrissionPage not installed. Install with: pip install DrissionPage")
    ChromiumPage = None

from app.crawlers.base_crawler import BaseCrawler
from app.crawlers.data_cleaner import DataCleaner


class JDCrawler(BaseCrawler):
    """京东爬虫"""

    JD_COMMENT_API = "https://club.jd.com/comment/productPageComments.action"
    JD_PRODUCT_URL_PATTERN = r"item\.jd\.com/(\d+)\.html"

    def __init__(self, timeout: int = 10, max_retries: int = 3, headless: bool = True):
        """
        初始化京东爬虫

        Args:
            timeout: 请求超时时间
            max_retries: 最大重试次数
            headless: 是否使用无头浏览器
        """
        super().__init__(timeout, max_retries)
        self.headless = headless
        self.page = None

    def _init_page(self):
        """初始化浏览器页面"""
        if ChromiumPage is None:
            raise ImportError("DrissionPage is not installed")

        if self.page is None:
            self.page = ChromiumPage()
            logger.info("Browser page initialized")

    def extract_product_id(self, url: str) -> str:
        """从京东 URL 提取商品 ID"""
        match = re.search(self.JD_PRODUCT_URL_PATTERN, url)
        if match:
            return match.group(1)

        raise ValueError(f"Invalid JD product URL: {url}")

    def normalize_product_url(self, url: str) -> str:
        """标准化商品链接"""
        product_id = self.extract_product_id(url)
        return f"https://item.jd.com/{product_id}.html"

    def fetch_product_info(self, url: str) -> Dict[str, Any]:
        """抓取商品基础信息"""
        normalized_url = self.normalize_product_url(url)
        product_id = self.extract_product_id(normalized_url)
        product_name = None

        if ChromiumPage is not None:
            try:
                self._init_page()
                self.page.get(normalized_url)
                self.page.wait.load_start()
                title_element = self.page.ele("xpath://div[contains(@class,'sku-name')]", timeout=3)
                if title_element:
                    product_name = DataCleaner.clean_text(title_element.text)
            except Exception as e:
                logger.warning(f"Failed to fetch JD product info by browser: {str(e)}")

        return {
            "source": "jd",
            "external_product_id": product_id,
            "product_url": normalized_url,
            "product_name": product_name,
        }

    def fetch_comments(self, product_id: str, page: int = 1) -> List[Dict[str, Any]]:
        """采集京东评论"""
        try:
            self._init_page()

            url = f"https://item.jd.com/{product_id}.html"
            self.page.get(url)
            logger.info(f"Accessed product page: {url}")

            self.page.wait.load_start()
            self.page.scroll.down(3)

            comments = []
            comment_elements = self.page.eles("xpath://div[contains(@class,'comment-item')]")

            for element in comment_elements:
                try:
                    comment_data = {
                        "content": element.ele("xpath:.//p[contains(@class,'comment-con')]").text,
                        "score": self._extract_score_from_element(element),
                        "comment_time": element.ele("xpath:.//span[contains(@class,'comment-time')]").text,
                        "source_comment_id": element.attr("data-comment-id"),
                    }
                    comments.append(comment_data)
                except Exception as e:
                    logger.warning(f"Failed to extract comment element: {str(e)}")
                    continue

            return comments

        except Exception as e:
            logger.error(f"Failed to fetch comments: {str(e)}")
            return []

    def parse_comment(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析单条评论"""
        return DataCleaner.clean_comment(comment_data)

    @staticmethod
    def _extract_score_from_element(element) -> Optional[int]:
        """从元素中提取评分"""
        try:
            score_class = element.attr("class") or ""
            match = re.search(r"score-(\d+)", score_class)
            if match:
                return int(match.group(1))

            score_text = element.ele("xpath:.//span[contains(@class,'score')]").text
            return DataCleaner.extract_score(score_text)
        except Exception:
            return None

    def close(self):
        """关闭浏览器"""
        if self.page:
            self.page.quit()
            logger.info("Browser closed")


class JDCrawlerSimple(BaseCrawler):
    """京东爬虫简化版（用于测试）"""

    def extract_product_id(self, url: str) -> str:
        """从京东 URL 提取商品 ID"""
        match = re.search(r"item\.jd\.com/(\d+)\.html", url)
        if match:
            return match.group(1)
        raise ValueError(f"Invalid JD product URL: {url}")

    def normalize_product_url(self, url: str) -> str:
        """标准化商品链接"""
        parsed = urlparse(url)
        normalized_source = url if parsed.scheme else f"https://{url.lstrip('/')}"
        product_id = self.extract_product_id(normalized_source)
        return f"https://item.jd.com/{product_id}.html"

    def fetch_product_info(self, url: str) -> Dict[str, Any]:
        """返回测试用商品基础信息"""
        product_id = self.extract_product_id(url)
        return {
            "source": "jd",
            "external_product_id": product_id,
            "product_url": self.normalize_product_url(url),
            "product_name": f"京东商品-{product_id}",
        }

    def fetch_comments(self, product_id: str, page: int = 1) -> List[Dict[str, Any]]:
        """采集京东评论（模拟数据）"""
        mock_comments = [
            {
                "content": "物流很快，包装完好，质量不错，值得购买",
                "score": 5,
                "comment_time": "2026-03-20",
                "source_comment_id": "123456"
            },
            {
                "content": "物流太慢了，从北京到上海用了7天，质量一般",
                "score": 2,
                "comment_time": "2026-03-19",
                "source_comment_id": "123457"
            },
            {
                "content": "价格有点贵，但质量还可以，服务态度不错",
                "score": 3,
                "comment_time": "2026-03-18",
                "source_comment_id": "123458"
            }
        ]

        page_size = 3
        start = (page - 1) * page_size
        end = start + page_size

        return mock_comments[start:end] if start < len(mock_comments) else []

    def parse_comment(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析单条评论"""
        return DataCleaner.clean_comment(comment_data)
