"""
京东爬虫实现
使用 DrissionPage 采集京东商品评论
"""

from json import JSONDecodeError, loads
import re
from time import perf_counter, sleep
from typing import List, Dict, Any, Optional
from urllib.parse import parse_qs, urlparse
from loguru import logger

try:
    from DrissionPage import ChromiumOptions, ChromiumPage
except ImportError:
    logger.warning("DrissionPage not installed. Install with: pip install DrissionPage")
    ChromiumOptions = None
    ChromiumPage = None

from app.crawlers.base_crawler import BaseCrawler
from app.crawlers.data_cleaner import DataCleaner
from app.config import (
    JD_CRAWLER_BROWSER_PATH,
    JD_CRAWLER_LOCAL_PORT,
    JD_CRAWLER_PROFILE,
    JD_CRAWLER_TIMEOUT,
    JD_CRAWLER_USE_SYSTEM_USER_PATH,
    JD_CRAWLER_USER_AGENT,
    JD_CRAWLER_USER_DATA_PATH,
)


class JDCrawler(BaseCrawler):
    """京东爬虫"""

    JD_COMMENT_REQUEST_URL = "api.m.jd.com/client.action"
    JD_PRODUCT_URL_PATTERN = r"item\.jd\.com/(\d+)\.html"
    JD_BLOCKED_URL_KEYWORDS = ("reason=403", "from=pc_item")
    JD_COMMENT_ENTRY_XPATH = "xpath://*[@id='comment-root']/div[3]/div"
    JD_COMMENT_SCROLL_TARGETS = (
        "xpath://*[@id='comment-root']//div[contains(@class,'comment-item')]",
        "xpath://*[@id='comment-root']//div[contains(text(),'最新')]",
        "xpath://*[@id='comment-root']",
    )

    def __init__(self, timeout: int = JD_CRAWLER_TIMEOUT, max_retries: int = 3, headless: bool = True):
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
        if ChromiumPage is None or ChromiumOptions is None:
            raise ImportError("DrissionPage is not installed")

        if self.page is None:
            options = ChromiumOptions().headless(self.headless)
            options.set_user_agent(JD_CRAWLER_USER_AGENT)

            if JD_CRAWLER_BROWSER_PATH:
                options.set_browser_path(JD_CRAWLER_BROWSER_PATH)

            if JD_CRAWLER_USE_SYSTEM_USER_PATH:
                options.use_system_user_path(True)
            elif JD_CRAWLER_USER_DATA_PATH:
                options.set_user_data_path(JD_CRAWLER_USER_DATA_PATH)

            if JD_CRAWLER_PROFILE:
                options.set_user(JD_CRAWLER_PROFILE)

            if JD_CRAWLER_LOCAL_PORT > 0:
                options.set_local_port(JD_CRAWLER_LOCAL_PORT)
            else:
                options.auto_port(True)

            self.page = ChromiumPage(options)
            logger.info(
                "Browser page initialized: headless={} profile={} use_system_user_path={} user_data_path={} browser_path={}",
                self.headless,
                JD_CRAWLER_PROFILE,
                JD_CRAWLER_USE_SYSTEM_USER_PATH,
                JD_CRAWLER_USER_DATA_PATH or "default",
                JD_CRAWLER_BROWSER_PATH or "default",
            )

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
                self._raise_if_blocked(normalized_url)
                self.page.wait.load_start()
                title_element = self.page.ele("xpath://span[contains(@class,'sku-title')]", timeout=3)
                logger.info(f"标题元素：{title_element}")
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
            self._raise_if_blocked(url)
            logger.info(f"进入产品页面: {url}")
            self.page.wait.doc_loaded()
            # 商品页主文档加载完成不代表评论区域已经稳定，额外等待评论根节点出现。
            self.page.ele("xpath://*[@id='comment-root']", timeout=10)
            sleep(1.5)
            self.page.listen.start(
                targets=self.JD_COMMENT_REQUEST_URL,
                method="POST",
            )
            # 先开启评论接口监听，再进入评论弹层，避免漏掉首次自动请求。
            self._open_comment_page()

            # page 参数在 JD 真爬虫里更接近“希望捕获的评论加载轮次”，不是传统页码。
            max_attempts = max(6, page)
            for attempt in range(1, max_attempts + 1):
                # 首次进入评论页会自动触发评论请求；查看更多评论时需要继续滚动评论页触发后续请求。
                if page > 1 or attempt > 1:
                    # 第 2 页及以后要靠评论弹层内部滚动，继续触发新的评论请求。
                    self._scroll_comment_page()

                comments = self._collect_comments_for_page(page=page, attempt=attempt)
                if comments:
                    logger.info(
                        "京东评论api返回评论: product_id={} round={} comment_count={}",
                        product_id,
                        page,
                        len(comments),
                    )
                    return comments

            logger.warning("监听器没有捕捉到评论: product_id={} round={}", product_id, page)
            return []

        except Exception:
            logger.exception("Failed to fetch comments")
            return []
        finally:
            if self.page:
                self.page.listen.pause(clear=True)

    def _raise_if_blocked(self, target_url: str) -> None:
        """检测商品页是否被京东重定向到 403 拦截页。"""
        if not self.page:
            return

        current_url = ""
        try:
            current_url = self.page.url or ""
        except Exception:
            current_url = ""

        if any(keyword in current_url for keyword in self.JD_BLOCKED_URL_KEYWORDS):
            raise RuntimeError(
                "JD product page blocked by anti-bot protection: "
                f"target_url={target_url} current_url={current_url}"
            )

    def parse_comment(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析单条评论"""
        return DataCleaner.clean_comment(comment_data)

    @staticmethod
    def _parse_request_payload(post_data: Any) -> Dict[str, Any]:
        """把监听到的 form-urlencoded 请求体拆成顶层字段和 body JSON。"""
        if not post_data:
            return {}

        if isinstance(post_data, dict):
            payload = dict(post_data)
        elif isinstance(post_data, str):
            payload = {
                key: values[0] if len(values) == 1 else values
                for key, values in parse_qs(post_data, keep_blank_values=True).items()
            }
        else:
            return {}

        raw_body = payload.get("body")
        if isinstance(raw_body, str):
            try:
                payload["body_json"] = loads(raw_body)
            except JSONDecodeError:
                payload["body_json"] = None
        elif isinstance(raw_body, dict):
            payload["body_json"] = raw_body
        else:
            payload["body_json"] = None
        return payload

    def _collect_comments_for_page(self, page: int, attempt: int) -> List[Dict[str, Any]]:
        """
        在短暂静默窗口中收集目标轮次的评论请求。

        首次进入评论弹层时，JD 可能会连续发出多次 `page=1` 请求。
        这里会在一个短窗口里把同轮次评论收齐后再去重。
        """
        target_page = str(page)
        overall_timeout = 8.0
        idle_timeout = 1.8
        start_time = perf_counter()
        deadline = start_time + overall_timeout
        collected_comments: List[Dict[str, Any]] = []
        matched_packets = 0

        while perf_counter() < deadline:
            remaining = max(0.2, deadline - perf_counter())
            packet = self.page.listen.wait(timeout=min(2.0, remaining), raise_err=False)
            if not packet:
                if matched_packets > 0:
                    break
                continue

            request_payload = self._parse_request_payload(packet.request.postData)
            if request_payload.get("functionId") != "getCommentListPage":
                continue

            body_payload = request_payload.get("body_json") or {}
            packet_page_num = str(body_payload.get("pageNum") or "")
            logger.info(
                "Captured JD comment request: target_round={} packet_page={} attempt={}",
                page,
                packet_page_num or "unknown",
                attempt,
            )
            if packet_page_num and packet_page_num != target_page:
                continue

            comments = self._extract_comments_from_response(packet.response.body)
            if not comments:
                continue

            matched_packets += 1
            collected_comments.extend(comments)
            # 命中目标页后，再留一个短暂静默窗口，等待同页后续自动请求补齐。
            deadline = min(start_time + overall_timeout, perf_counter() + idle_timeout)

        return self._deduplicate_comments(collected_comments)

    def _open_comment_page(self) -> None:
        """滚动到“全部评论”按钮并点击，进入评论页。"""
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self.page.run_js("window.scrollTo(0, document.body.scrollHeight * 0.7);")
                sleep(1.2)

                entry_button = self.page.ele(self.JD_COMMENT_ENTRY_XPATH, timeout=6)
                if not entry_button:
                    raise RuntimeError("JD comment entry button not found")

                entry_button.scroll.to_see()
                sleep(0.8)

                # 页面滚动后可能触发重渲染，点击前重新定位一次，避免操作失效元素。
                entry_button = self.page.ele(self.JD_COMMENT_ENTRY_XPATH, timeout=3)
                if not entry_button:
                    raise RuntimeError("JD comment entry button lost after scroll")

                entry_button.click(by_js=True)
                sleep(2)
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "进入评论页失败，准备重试: attempt={} error={}",
                    attempt,
                    str(e),
                )
                sleep(1)

        raise RuntimeError(f"JD comment entry button click failed: {last_error}")

    def _scroll_comment_page(self) -> None:
        """在评论页持续向下滚动，触发下一批评论接口请求。"""
        scroll_target = self._find_comment_scroll_target()
        if not scroll_target:
            logger.warning("评论对话框可滚动对象没找到，回退到窗口滚动")
            self.page.run_js("window.scrollBy(0, 1600);")
            sleep(1.2)
            return

        # 手工滚动时，滚轮是在评论区域内部触发的，这里也把滚轮事件打到弹层内部元素。
        scroll_target.scroll.to_see()
        self.page.actions.scroll(delta_y=1800, on_ele=scroll_target)
        sleep(1.2)
        self.page.actions.scroll(delta_y=1800, on_ele=scroll_target)
        sleep(1.2)

    def _find_comment_scroll_target(self):
        """在评论对话框内找到一个可见的元素接受滚动事件"""
        for locator in self.JD_COMMENT_SCROLL_TARGETS:
            target = self.page.ele(locator, timeout=2)
            if target:
                return target
        return None

    @classmethod
    def _extract_comments_from_response(cls, response_body: Any) -> List[Dict[str, Any]]:
        """按 result -> floors[mId=commentlist-list] -> data[] -> commentInfo{} 解析评论。"""
        comment_items = cls._extract_comment_items(response_body)
        comments: List[Dict[str, Any]] = []
        for item in comment_items:
            comment_info = item.get("commentInfo")
            if not isinstance(comment_info, dict):
                continue

            # 当前真实接口里，评论正文、评分、时间、唯一 ID 都挂在 commentInfo 下。
            content = cls._pick_text(comment_info, "commentData", "tagCommentContent", "commentContent")

            comments.append(
                {
                    "content": content or "",
                    "score": comment_info.get("commentScore") or comment_info.get("score") or comment_info.get("scoreLevel"),
                    "comment_time": comment_info.get("commentDate") or comment_info.get("newCommentDate"),
                    "source_comment_id": comment_info.get("guid") or comment_info.get("commentId"),
                }
            )
        return comments

    @classmethod
    def _extract_comment_items(cls, response_body: Any) -> List[Dict[str, Any]]:
        """从评论接口响应体中提取 floors 里的评论卡片列表。"""
        if not isinstance(response_body, dict):
            return []

        result = response_body.get("result")
        if not isinstance(result, dict):
            return []

        floors = result.get("floors")
        if not isinstance(floors, list):
            return []

        for floor in floors:
            if not isinstance(floor, dict):
                continue
            if floor.get("mId") != "commentlist-list":
                continue

            data = floor.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        return []

    @staticmethod
    def _pick_text(item: Dict[str, Any], *keys: str) -> Optional[str]:
        """从多个候选字段里取第一个非空文本值。"""
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _deduplicate_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate comments by source_comment_id, with content as fallback."""
        deduplicated: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()
        for comment in comments:
            source_comment_id = str(comment.get("source_comment_id") or "").strip()
            content = str(comment.get("content") or "").strip()
            key = source_comment_id or content
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            deduplicated.append(comment)
        return deduplicated

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
