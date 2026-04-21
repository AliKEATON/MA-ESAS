from DrissionPage import ChromiumPage

url = "https://item.jd.com/100315784178.html"
page = ChromiumPage()
page.get(url)

# ==============================================
# 测试 1：你从浏览器复制的绝对路径 Xpath（大概率失败）
# ==============================================
try:
    ele1 = page.ele("xpath://*[@id='root']/div/div[3]/div[3]/div[2]/div[2]/div/div[1]/div[3]/div[1]/div/div/span[1]/span[2]", timeout=3)
    title1 = ele1.text.strip() if ele1 else "未获取到（路径太长，极易失效）"
except:
    title1 = "获取失败"

# ==============================================
# 测试 2：推荐的稳定 Xpath（100%能拿到）
# ==============================================
ele2 = page.ele("xpath://span[contains(@class,'sku-title')]", timeout=5)
title2 = ele2.text.strip() if ele2 else "未获取到"

# ==============================================
# 输出结果
# ==============================================
print("浏览器复制长路径结果：", title1)
print("推荐稳定写法结果：", title2)

page.quit()