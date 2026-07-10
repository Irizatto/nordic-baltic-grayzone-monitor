# Nordic-Baltic Gray Zone & Submarine Infrastructure Monitor

## What this is / 这是什么

A small, open-source OSINT dashboard for organizing maritime **risk signals**, anomalies, and review priorities around undersea infrastructure in the Baltic Sea, Nordic High North, and Arctic approaches. It is designed to support careful human review.

这是一个小型开源 OSINT 仪表板，用于整理波罗的海、北欧高北地区和北极通道附近海底基础设施的海事**风险信号**、异常和审查优先级，服务于谨慎的人工研判。

## What this is not / 这不是什么

It does not determine guilt, intent, legal responsibility, or state attribution. A score is a review priority, not an accusation. The initial version deliberately uses fictional mock data only; it has no live tracking or external APIs.

它不判断罪责、意图、法律责任或国家归因。分数仅代表审查优先级，并非指控。初始版本刻意只使用虚构模拟数据，不含实时跟踪或外部 API。

## Open the dashboard / 打开仪表板

1. Open this project folder in File Explorer.
2. Open the `docs` folder.
3. Double-click `index.html`. It opens in your web browser.

If your browser limits loading local data files, start a simple local web server from the project folder: `python -m http.server`, then open `http://localhost:8000/docs/`. The site always includes a committed mock dataset.

如果浏览器限制读取本地数据文件，可在项目文件夹运行 `python -m http.server`，然后打开 `http://localhost:8000/docs/`。网站始终包含已提交的模拟数据集。

## GitHub Pages / GitHub Pages 部署

GitHub Pages can publish the `docs/` folder directly. In the repository’s GitHub settings, choose **Pages**, select **Deploy from a branch**, then select the desired branch and `/docs` folder. No build step is required.

GitHub Pages 可直接发布 `docs/` 文件夹。在仓库 GitHub 设置中选择 **Pages**，选择 **Deploy from a branch**，再选择相应分支与 `/docs` 文件夹。无需构建步骤。

## Project layout / 项目结构

- `docs/` — the static website served by GitHub Pages, including its mock data.
- `src/` — the Python mock-data generator and future data-pipeline helpers.
- `data/reference/` — small, human-readable reference lists.
- `data/raw/`, `data/processed/`, `data/events/` — reserved for future, safely preserved pipeline inputs and outputs.
- `.env.example` — names of optional future credentials; it contains no secrets.

## Refresh mock data / 刷新模拟数据

With Python 3.11+ installed, run:

```text
python src/generate_dashboard_data.py
```

On a new checkout this creates the fictional dashboard data and records the mock fallback in `docs/data/metadata.json`. If those files already exist, the generator preserves them in line with the project’s no-overwrite rule.

## Disclaimer / 免责声明

Risk scores are review priorities, not legal or attribution determinations. All current positions, vessels, infrastructure references, SAR detections, and rule evidence are fictional mock data for interface development.

风险分数是审查优先级，而非法律或归因判定。当前所有位置、船舶、基础设施参考、SAR 探测和规则证据均为用于界面开发的虚构模拟数据。

Released under the [MIT License](https://opensource.org/license/mit).
