# 微信公众号文章抓取脚本 — 使用文档

> 脚本文件：`vx\\\\\\\_article\\\\\\\_scraper.py`
> 版本：v6.0（代码内部分注释标记为 v6.1，详见\\\\\\\[版本说明](#版本说明)）
> 原作者：yifei zhang ｜ 最后更新：2026-05-26

\---

## 一、这个脚本是做什么的

把一篇**微信公众号文章**一键转换成可直接粘贴进 **WordPress** 后台的「纯净 HTML 片段」，并自动把文章里的图片下载到本地、把正文里的图片地址替换成 WordPress 媒体库的真实 URL。

适用场景：把公司公众号已发布的内容搬运 / 同步到官网（`somaagent.com.cn`）。

一句话流程：

```
微信文章链接  →  抓取  →  下图  →  清洗  →  校验图片URL  →  output/xxx\\\\\\\_wp\\\\\\\_clean.html  →  粘贴进WP
```

\---

## 二、运行环境与依赖

### 依赖库

|库|用途|
|-|-|
|`playwright`|无头浏览器，抓取微信文章完整渲染后的 HTML（微信正文是 JS 动态加载的，普通 requests 抓不全）|
|`beautifulsoup4`|解析、清洗 HTML|
|`requests`|下载图片、调用 WordPress REST API|

标准库：`os`、`re`、`hashlib`（无需安装）。

### 安装步骤

```bash
# 1. 安装 Python 依赖
pip install playwright beautifulsoup4 requests

# 2. 安装 Playwright 的浏览器内核（关键，容易漏）
playwright install chromium
```

> ⚠️ 第 2 步必须执行，否则运行时会报「找不到浏览器可执行文件」。

\---

## 三、运行前必改的两个配置

打开脚本，顶部有两处需要根据情况修改：

```python
# 第 15 行：要抓取的微信文章链接
URL = "https://mp.weixin.qq.com/s/hOkZZ\\\\\\\_wzelByXVH7bO2nqA"

# 第 19 行：WordPress 媒体库 URL 前缀（一般固定，换站点才改）
WP\\\\\\\_MEDIA\\\\\\\_BASE = "https://www.somaagent.com.cn/wp-content/uploads"
```

* **每抓一篇新文章，只需改 `URL`。**
* `WP\\\\\\\_MEDIA\\\\\\\_BASE` 指向 WordPress 上传目录，除非换域名 / 换站点，否则不用动。

\---

## 四、怎么用（标准操作流程）

因为「校验图片真实 URL」需要图片**已经上传到 WordPress 媒体库**，而图片又是脚本第一次运行才下载出来的，所以存在先后顺序问题。推荐按下面两步走：

### 第 1 步：抓取 + 下载图片

1. 改好 `URL`。
2. 运行：

```bash
   python vx\\\\\\\_article\\\\\\\_scraper.py
   ```

3. 此时 `output/` 目录下生成：

   * 若干图片文件：`{标题slug}\\\\\\\_0.png`、`{标题slug}\\\\\\\_1.jpg` …
   * 一个 HTML 文件：`{标题}\\\\\\\_wp\\\\\\\_clean.html`
4. 首次运行时，由于图片还没传到 WP，终端会提示「未校验 WP URL」，这是**正常**的。

### 第 2 步：上传图片 → 重跑校验

1. 把 `output/` 里的所有图片**上传到 WordPress 媒体库**。
2. **不改任何配置，再次运行脚本**：

```bash
   python vx\\\\\\\_article\\\\\\\_scraper.py
   ```

3. 这次脚本会通过 WordPress REST API 查询媒体库，匹配出每张图片的真实 URL（自动处理 `.jpg/.png` 格式差异和 `-scaled` 后缀问题），重新生成 HTML。
4. 终端显示 `图片URL已通过WP API校验，粘贴即用 ✅` 即成功。

### 第 3 步：粘贴进 WordPress

打开 WP 后台 → 新建文章 → 切换到「**代码编辑器**」（不是可视化编辑器）→ 打开 `output/xxx\\\\\\\_wp\\\\\\\_clean.html`，全选复制粘贴即可。正文文字、图片、顺序都已保留并带好内联样式。

> 💡 如果不想跑两遍：第一遍生成的 HTML 里图片 URL 是「按发布年月拼出来的猜测路径」（如 `.../2026/05/xxx\\\\\\\_0.png`）。只要上传时不改文件名、上传月份与文章发布月份一致，多数情况也能直接用；但 WP 对超大图会加 `-scaled` 后缀、对 jpg 可能转格式，所以\\\\\\\*\\\\\\\*强烈建议跑第二遍做校验\\\\\\\*\\\\\\\*。

\---

## 五、输出文件说明

所有产物都在脚本同级的 `output/` 目录（自动创建）：

|文件|说明|
|-|-|
|`{slug}\\\\\\\_{序号}.{格式}`|下载的正文图片，格式由实际内容自动识别（PNG/JPG/WEBP/GIF）|
|`{标题}\\\\\\\_wp\\\\\\\_clean.html`|最终交付物：纯净 HTML 片段，含正文文字 + 图片，图片已指向 WP 媒体库 URL|

图片命名里的 `{slug}` 规则（见 `slugify()`）：`月日 - 标题ASCII部分 - 标题MD5前8位`，整体截断到 40 字符，保证文件名唯一且为纯 ASCII。例如 `0512-ATH-1.0-c583cd0a`。

\---

## 六、代码结构 / 函数速查

脚本是单文件、面向过程，主流程在 `if \\\\\\\_\\\\\\\_name\\\\\\\_\\\\\\\_ == "\\\\\\\_\\\\\\\_main\\\\\\\_\\\\\\\_"`（第 410 行起）。各函数职责：

|函数|作用|
|-|-|
|`fetch\\\\\\\_html(url)`|用 Playwright 打开页面，等 5 秒让 JS 渲染完，返回完整 HTML|
|`parse\\\\\\\_content(html)`|从 HTML 中提取标题（`h1#activity-name`）、发布时间（`#publish\\\\\\\_time`）、正文（`div#js\\\\\\\_content`）|
|`slugify(text, publish\\\\\\\_time)`|生成纯 ASCII 的文件名前缀（日期 + ASCII + 哈希）|
|`download\\\\\\\_images(content, slug)`|遍历正文 `<img>`，下载图片到本地，并把 `src` 改成本地文件名|
|`\\\\\\\_detect\\\\\\\_image\\\\\\\_ext(data, ct)`|通过 magic bytes（文件头字节）+ Content-Type 判断真实图片格式|
|`deep\\\\\\\_clean(content)`|**核心清洗**：去掉微信的 data-\*/style/class/id、空标签、隐藏元素、`mp-` 自定义标签、script，并简化多余嵌套|
|`verify\\\\\\\_wp\\\\\\\_urls(slug, n, subpath)`|调 WP REST API（`/wp-json/wp/v2/media`）查媒体库，把本地文件名映射到真实 URL|
|`\\\\\\\_extract\\\\\\\_wp\\\\\\\_subpath(publish\\\\\\\_time)`|从发布时间推算 WP 媒体库的 `年/月` 子路径（如 `2026/05`）|
|`save\\\\\\\_wp\\\\\\\_clean\\\\\\\_html(...)`|把清洗后的正文 + 图片 URL + 内联样式，组装成最终 HTML 文件|

### 清洗白名单（第 28 行 `ALLOWED\\\\\\\_ATTRS`）

清洗时只保留下列标签的下列属性，其余属性一律删除：

```
img   → src, alt, width, height
a     → href, target
td/th → colspan, rowspan
table → border
```

如需保留更多属性（比如某些表格样式），改这里。

\---

## 七、注意事项

1. **必须 `playwright install chromium`**，只 `pip install` 不够。
2. **微信有抓取频率限制**：短时间内大量请求同一文章/图片可能触发风控，间隔着抓。
3. **`page.wait\\\\\\\_for\\\\\\\_timeout(5000)` 是写死的 5 秒**（`fetch\\\\\\\_html` 内）。网络慢导致正文没加载完时，可调大；想提速可调小。
4. **校验 URL 依赖 WP API 可公开访问**：`/wp-json/wp/v2/media` 接口需能匿名读取。若站点关闭了 REST API 或加了鉴权，第 2 步会跳过校验（返回空映射），此时 HTML 用的是「拼接猜测的 URL」。
5. **图片必须先上传 WP 才能校验**，顺序不能反，见[第四节](#四怎么用标准操作流程)。
6. **必须用 WP「代码编辑器」粘贴**，用可视化编辑器会把内联样式和结构吃掉。
7. **DOM 选择器依赖微信现有页面结构**（`#activity-name` / `#publish\\\\\\\_time` / `#js\\\\\\\_content`）。如果将来微信改版，`parse\\\\\\\_content` 抓不到内容就要更新这几个选择器。
8. 选择器抓不到时的兜底：标题返回「无标题」、时间返回空串、正文返回 `None`，脚本不会崩但输出会不完整，留意终端打印的标题/时间是否正常。

\---

## 八、版本说明

* 文件头与主流程标记为 **v6.0**：修复图片格式检测（不再一律存成 `.jpg`，改为按真实格式存 `.png/.webp/.gif`），新增 WP REST API 的 URL 校验。
* `save\\\\\\\_wp\\\\\\\_clean\\\\\\\_html()` 的文档字符串里标记为 **v6.1**：完整保留正文「文字 + 图片」并按原文顺序输出，图片替换为 WP 媒体库完整 URL 并加统一样式。
* 两处版本号不一致属于历史遗留，**实际功能以代码为准**，不影响使用。接手后若再迭代，建议统一版本号。

