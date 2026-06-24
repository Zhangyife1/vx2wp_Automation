# 微信公众号文章抓取脚本 v6.0
# 作者：yifei zhang
# 5.19.2026
# updated: 5.26.2026 - v6.0 修复图片格式检测（.jpg→.png），新增WP REST API URL校验


from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, Tag, NavigableString
import os
import requests
import re
import hashlib

# ===== 复制vx公众号链接到这里 =====
URL = "https://mp.weixin.qq.com/s/i-GX1SF405h2sQcb_pnqIA" 

# WP 媒体库 URL 前缀（图片上传后的访问路径）
# 格式：https://你的域名/wp-content/uploads/YYYY/MM/
WP_MEDIA_BASE = "https://www.somaagent.com.cn/wp-content/uploads"

# ===== 自动设置路径 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== 微信保留属性白名单 =====
ALLOWED_ATTRS = {
    "img":   ["src", "alt", "width", "height"],
    "a":     ["href", "target"],
    "td":    ["colspan", "rowspan"],
    "th":    ["colspan", "rowspan"],
    "table": ["border"],
}


def slugify(text, publish_time=""):
    # 1. 提取日期前缀（月日，4位数字，保证唯一性）
    date_prefix = ""
    date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', publish_time)
    if date_match:
        date_prefix = f"{date_match.group(2).zfill(2)}{date_match.group(3).zfill(2)}"
    
    # 2. 提取ASCII部分（字母、数字、横线、点）
    #    先将空格转横线，再清除非安全字符
    ascii_part = text.encode('ascii', 'ignore').decode('ascii')
    ascii_part = ascii_part.replace(' ', '-')
    ascii_part = re.sub(r'[^a-zA-Z0-9\-\.]', '', ascii_part)
    ascii_part = re.sub(r'-+', '-', ascii_part).strip('-')
    if not ascii_part:
        ascii_part = 'vx'
    
    # 3. 标题哈希（取前8位，保证唯一性）
    title_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    
    # 4. 组合：日期-ASCII-哈希，截断到40字符
    result = f"{date_prefix}-{ascii_part}-{title_hash}" if date_prefix else f"{ascii_part}-{title_hash}"
    return result[:40]


def fetch_html(url):
    """用 Playwright 抓取微信文章完整HTML"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(5000)
        html = page.content()
        browser.close()
        return html


def parse_content(html):
    """提取标题、发布时间、正文内容"""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1", id="activity-name")
    title = title_tag.get_text(strip=True) if title_tag else "无标题"

    time_tag = soup.find(id="publish_time")
    publish_time = time_tag.get_text(strip=True) if time_tag else ""

    content = soup.find("div", id="js_content")

    return title, publish_time, content


def _detect_image_ext(img_data, content_type=""):
    """
    检测图片实际格式，返回正确的文件扩展名
    
    优先级：magic bytes > Content-Type > 默认.jpg
    """
    # 1. 检测 magic bytes（最可靠）
    if img_data[:8] == b'\x89PNG\r\n\x1a\n':
        return ".png"
    if img_data[:3] == b'\xff\xd8\xff':
        return ".jpg"
    if img_data[:4] == b'RIFF' and img_data[8:12] == b'WEBP':
        return ".webp"
    if img_data[:4] == b'GIF8':
        return ".gif"
    
    # 2. 从 Content-Type 推断
    ct = content_type.lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    
    # 3. 默认 .jpg
    return ".jpg"


def download_images(content, title_slug):
    """
    下载图片到本地，src 替换为本地文件名
    文件名格式：{title_slug}_{序号}.{实际格式}
    自动检测图片真实格式（PNG/JPG/WEBP），不再一律用 .jpg
    """
    for i, img in enumerate(content.find_all("img")):
        img_url = (
            img.get("data-src") or
            img.get("data-original") or
            img.get("src")
        )

        if not img_url:
            continue

        try:
            resp = requests.get(img_url, timeout=10)
            img_data = resp.content
            content_type = resp.headers.get("Content-Type", "")
            
            # 检测实际图片格式
            ext = _detect_image_ext(img_data, content_type)
            filename = f"{title_slug}_{i}{ext}"
            file_path = os.path.join(OUTPUT_DIR, filename)

            with open(file_path, "wb") as f:
                f.write(img_data)

            img["src"] = filename
            print(f"   [{i}] {filename} ({content_type})")

        except Exception as e:
            print(f"图片下载失败: {img_url} ({e})")

    return content


def deep_clean(content):
    """
    深度清洗HTML，输出纯净片段可直接粘贴到WP代码编辑器

    清洗规则：
    1. 删除所有微信 data-* 属性
    2. 删除所有内联 style 属性
    3. 删除所有 class 属性
    4. 删除所有 id 属性
    5. 删除空标签（无文本无图片的标签）
    6. 删除微信专用标签（mp-common-* 等）
    7. 删除 script / noscript 标签
    8. 简化嵌套：连续单层 section/p 嵌套只保留最内层
    9. 图片只保留 src 和 alt
    10.剥离外层 js_content 包裹 div
    """
    if content is None:
        return None

    # 0. 剥离外层 js_content 包裹
    #    用新 div 包裹内部子元素，避免 unwrap() 导致类型丢失
    if content.name == "div" and content.get("id") == "js_content":
        new_wrapper = BeautifulSoup("<div></div>", "html.parser").div
        for child in list(content.children):
            new_wrapper.append(child.__copy__() if isinstance(child, Tag) else NavigableString(str(child)))
        content = new_wrapper

    # 1. 删除 script / noscript
    for tag in content.find_all(["script", "noscript"]):
        tag.decompose()

    # 2. 删除微信专用自定义标签（mp-common-* 等）
    for tag in content.find_all(re.compile(r"^mp-")):
        tag.decompose()

    # 3. 删除隐藏元素（visibility: hidden / display: none）
    for tag in content.find_all(True):
        style = tag.get("style", "")
        if "display:none" in style.replace(" ", "").lower() or "visibility:hidden" in style.replace(" ", "").lower():
            tag.decompose()

    # 4. 逐标签清洗属性
    for tag in content.find_all(True):
        tag_name = tag.name
        allowed = ALLOWED_ATTRS.get(tag_name, [])

        # 只保留白名单属性
        attrs_to_delete = [k for k in tag.attrs if k not in allowed]
        for attr in attrs_to_delete:
            del tag[attr]

        # 图片特殊处理：确保有 alt
        if tag_name == "img" and not tag.get("alt"):
            tag["alt"] = ""

    # 5. 删除空标签（递归，从内到外）
    def remove_empty_tags(soup):
        changed = True
        while changed:
            changed = False
            for tag in soup.find_all(True):
                if tag.name == "img":
                    continue
                text = tag.get_text(strip=True)
                has_img = tag.find("img") is not None
                has_link = tag.name == "a" and tag.get("href")
                if not text and not has_img and not has_link:
                    tag.decompose()
                    changed = True

    remove_empty_tags(content)

    # 6. 简化嵌套：单子节点 section/p/span/div 嵌套 → 解包
    def unwrap_single_wrappers(soup):
        changed = True
        while changed:
            changed = False
            for tag in soup.find_all(["section", "p", "span", "div"]):
                children = [c for c in tag.children if isinstance(c, Tag)]
                own_text = tag.string or ""
                # 只有一个子标签且无自身文本 → 解包
                if len(children) == 1 and not own_text.strip():
                    tag.unwrap()
                    changed = True
                # 无子标签但有多个img（公众号常见：span里并排多个img）→ 解包
                if len(children) > 1 and not own_text.strip():
                    non_img_children = [c for c in children if c.name not in ("img", "br")]
                    if not non_img_children:
                        tag.unwrap()
                        changed = True

    unwrap_single_wrappers(content)

    # 7. 最终清理：剥离最外层多余包裹
    while True:
        top_tags = [c for c in content.children if isinstance(c, Tag)]
        if len(top_tags) == 1:
            top = top_tags[0]
            if top.name in ("div", "section", "span", "p"):
                top.unwrap()
                continue
        break

    return content


def verify_wp_urls(title_slug, num_images, wp_subpath):
  
    print(f"\n🔍 查询WP媒体库验证图片URL...")
    
    try:
        api_url = f"{WP_MEDIA_BASE.rsplit('/wp-content', 1)[0]}/wp-json/wp/v2/media"
        resp = requests.get(
            api_url,
            params={"per_page": 50, "orderby": "date", "order": "desc"},
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"   ⚠️ WP API 返回 {resp.status_code}，跳过URL校验")
            return {}
        
        items = resp.json()
        url_map = {}
        
        for item in items:
            source_url = item.get("source_url", "")
            if not source_url:
                continue
            
            # 从 source_url 提取文件名（含扩展名）
            # 例：https://.../2026/05/0512-ATH-1.0-c583cd0a_3-scaled.png
            url_filename = source_url.split("/")[-1]  # 0512-ATH-1.0-c583cd0a_3-scaled.png
            
            # 去掉 -scaled 后缀和扩展名，得到基础名
            base_name = url_filename.rsplit(".", 1)[0]  # 去掉扩展名
            base_name = re.sub(r'-scaled$', '', base_name)  # 去掉-scaled
            
            # 尝试匹配本地文件名
            for i in range(num_images):
                for ext in [".jpg", ".png", ".webp", ".gif"]:
                    local_name = f"{title_slug}_{i}{ext}"
                    local_base = local_name.rsplit(".", 1)[0]
                    
                    if base_name == local_base:
                        url_map[local_name] = source_url
                        break
        
        if url_map:
            print(f"   ✅ 找到 {len(url_map)}/{num_images} 张图片的实际URL")
            for k, v in url_map.items():
                print(f"   {k} → {v.split('/')[-1]}")
        else:
            print(f"   ⚠️ 未在WP媒体库找到匹配图片，请确认已上传")
        
        return url_map
        
    except Exception as e:
        print(f"   ⚠️ WP API 查询失败: {e}")
        return {}


def save_wp_clean_html(title, publish_time, content, title_slug, wp_url_map=None):
    """
    保存纯净HTML片段（WP代码编辑器可直接粘贴）
    v6.1 修复：完整保留正文【文字 + 图片】，按原文顺序输出。
          图片 src 替换为 WP 媒体库完整 URL 并加统一样式；文字段落原样保留。

    wp_url_map: 可选，来自 verify_wp_urls() 的实际URL映射
                如果提供，优先使用实际URL（解决 .jpg/.png 和 -scaled 问题）
    """
    # Windows文件名禁止字符: \ / : * ? " < > |
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
    filepath = os.path.join(OUTPUT_DIR, f"{safe_title}_wp_clean.html")

    # 确保 content 是可操作的 Tag/Soup
    if not isinstance(content, Tag):
        content = BeautifulSoup(str(content), "html.parser")

    # 自动推算 WP 媒体库的年/月子路径
    wp_subpath = _extract_wp_subpath(publish_time)

    # 遍历正文中的每张图片：只替换 src + 加样式，不改变它在正文中的位置
    imgs = content.find_all("img")
    for i, img in enumerate(imgs):
        local_src = img.get("src", "")

        # 优先使用 WP API 返回的实际 URL（解决格式和 -scaled 问题）
        wp_src = None
        if wp_url_map and local_src in wp_url_map:
            wp_src = wp_url_map[local_src]

        if wp_src:
            src = wp_src
        elif local_src and not local_src.startswith("http"):
            # 回退：拼接 WP 完整 URL
            src = f"{WP_MEDIA_BASE}/{wp_subpath}/{local_src}"
        else:
            src = local_src

        img["src"] = src
        if not img.get("alt"):
            img["alt"] = f"{title} - {i + 1}"
        # 统一图片样式（内联，避免被编辑器过滤）
        img["style"] = "width:100%;height:auto;display:block;margin:20px auto;"

    # 关键修复：输出整段正文的内部 HTML（文字段落 + 图片，按原文顺序）
    body_html = content.decode_contents()

    html = f"""<!-- 文章标题：{title} -->
<!-- 发布时间：{publish_time} -->
<!-- 正文【文字 + {len(imgs)}张图片】已按原文顺序输出；图片src为WP媒体库URL，粘贴即用 -->

<div style="text-align:center; color:#888; margin-bottom:20px;">{publish_time}</div>

<style>
.wx-article-content {{ line-height: 1.9; font-size: 16px; color: #333; word-break: break-word; }}
.wx-article-content p,
.wx-article-content section {{ margin: 0 0 16px; }}
</style>

<div class="wx-article-content">
{body_html}
</div>
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ WP纯净HTML已保存: {filepath}")
    print(f"   正文文字已保留，共输出 {len(imgs)} 张图片")
    print(f"   图片URL前缀: {WP_MEDIA_BASE}/{wp_subpath}/")
    return filepath


def _extract_wp_subpath(publish_time):
    """
    从发布时间提取 WP 媒体库的年/月子路径
 
    """
    match = re.search(r'(\d{4})年(\d{1,2})月', publish_time)
    if match:
        year = match.group(1)
        month = match.group(2).zfill(2)
        return f"{year}/{month}"
    # 回退：使用当前年月
    from datetime import datetime
    now = datetime.now()
    return f"{now.year}/{now.month:02d}"






if __name__ == "__main__":
    print("=" * 50)
    print("微信公众号文章抓取 v6.0（智能格式检测 + WP URL校验）")
    print("=" * 50)

    # 1. 抓取
    print("\n📥 抓取页面...")
    html = fetch_html(URL)
    title, publish_time, content = parse_content(html)
    print(f"   标题: {title}")
    print(f"   时间: {publish_time}")

    # 生成文章标题slug（纯ASCII，用于图片命名）
    title_slug = slugify(title, publish_time)
    print(f"   文件名前缀: {title_slug}")

    # 2. 下载图片（自动检测格式：PNG/JPG/WEBP）
    print("\n🖼️ 下载图片...")
    content = download_images(content, title_slug)

    # 3. 深度清洗
    print("\n🧹 深度清洗HTML...")
    content = deep_clean(content)

    # 4. 统计图片数
    if isinstance(content, Tag):
        num_imgs = len(content.find_all("img"))
    else:
        num_imgs = len(BeautifulSoup(str(content), "html.parser").find_all("img"))
    wp_subpath = _extract_wp_subpath(publish_time)

    # 5. WP URL 校验（需要图片已上传到WP媒体库）
    wp_url_map = verify_wp_urls(title_slug, num_imgs, wp_subpath)

    # 6. 保存WP纯净HTML
    print("\n💾 保存文件...")
    wp_file = save_wp_clean_html(title, publish_time, content, title_slug, wp_url_map)

    print(f"\n{'=' * 50}")
    print(f"✅ 完成！WP纯净HTML: {wp_file}")
    if wp_url_map:
        print(f"   → 图片URL已通过WP API校验，粘贴即用 ✅")
    else:
        print(f"   → ⚠️ 未校验WP URL，可能存在格式/后缀不匹配")
        print(f"   → 解决方法：上传图片后重新运行脚本，或手动替换URL")
    print(f"   → 在WP后台 → 新文章 → 代码编辑器 → 粘贴即可")
    print(f"{'=' * 50}")
