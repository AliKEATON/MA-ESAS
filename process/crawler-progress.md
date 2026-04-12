# 爬虫模块完善进度

## 本次调整
- 为 `BaseCrawler` 增加 `fetch_product_info()` 抽象方法，用于抽取商品基础信息。
- 为 `JDCrawler` / `JDCrawlerSimple` 增加商品信息抓取与链接标准化能力。
- 在 `CrawlerService` 中新增按商品链接解析、建档并爬取的入口。
- 在 `CrawlerService` 中沉淀 `get_product_status()`，移除路由文件里的动态补丁式绑定。
- 为爬虫接口新增 `POST /api/crawlers/crawl`，支持直接传商品链接独立调试该模块。
- 保留 `POST /api/crawlers/{product_id}/crawl` 兼容按内部商品 ID 触发爬取。

## 当前边界
- 当前仍默认使用 `JDCrawlerSimple` 作为稳定测试实现。
- 已为真实 `JDCrawler` 预留商品信息抓取能力，但页面选择器仍需按京东真实页面继续打磨。
- 该模块现在可以在不依赖完整分析任务流的情况下单独完善和联调。

## 建议下一步
1. 把 `JDCrawlerSimple` 切换策略改成配置驱动，例如开发环境使用 simple，真实环境使用 `JDCrawler`。
2. 为 `POST /api/crawlers/crawl` 增加专门的接口测试。
3. 补充商品新鲜度判断逻辑，例如基于 `last_crawled_at` 控制是否重复抓取。
4. 若后续要做多平台，继续按 `BaseCrawler` 扩展 `TaobaoCrawler` / `TmallCrawler`。
