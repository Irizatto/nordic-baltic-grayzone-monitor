# Nordic-Baltic Gray Zone & Submarine Infrastructure Monitor

An open-source OSINT dashboard for organizing maritime **risk signals**, anomalies, review priorities, and leads for human review around critical undersea infrastructure in the Baltic Sea, Nordic High North, and Arctic approaches.

这是一个开源 OSINT 仪表板，用于整理波罗的海、北欧高北地区及北极通道关键海底基础设施附近的**风险信号**、异常、审查优先级和人工复核线索。

The project does not determine intent, guilt, legal responsibility, or state attribution. Every automated output requires human assessment. / 本项目不判断意图、罪责、法律责任或国家归因；所有自动输出均需人工评估。

## Published site / 已发布网站

GitHub Pages serves the static site from `docs/`. The dashboard uses vanilla HTML, CSS, JavaScript, Leaflet.js, and Chart.js; no frontend build step is required.

GitHub Pages 从 `docs/` 目录发布静态网站。前端使用原生 HTML、CSS、JavaScript、Leaflet.js 和 Chart.js，无需构建步骤。

## Data sources and fallbacks / 数据源与回退

- Fintraffic Digitraffic AIS: open data, no API key required.
- BarentsWatch AIS: optional OAuth client credentials.
- Global Fishing Watch SAR: optional API token and dataset permission.
- Clearly labelled mock AIS/SAR records keep the site functional when a source or credential is unavailable.
- Infrastructure routes and areas in this stage are schematic and are not precise operational positions.

- Fintraffic Digitraffic AIS：开放数据，无需 API 密钥。
- BarentsWatch AIS：可选 OAuth 客户端凭据。
- Global Fishing Watch SAR：可选 API 令牌及数据集权限。
- 当数据源或凭据不可用时，系统使用明确标注的模拟 AIS/SAR 记录保持网站可用。
- 当前阶段的基础设施路线和区域均为示意数据，并非精确运营位置。

No secret belongs in the repository. Copy `.env.example` to `.env` for local use and fill only the credentials you have; GitHub Actions uses repository Secrets. / 仓库中不得保存任何密钥。本地可将 `.env.example` 复制为 `.env`，只填写已有凭据；GitHub Actions 使用仓库 Secrets。

## Run locally / 本地运行

With Python 3.11 or newer:

```text
python -m pip install -r requirements.txt
python src/generate_dashboard_data.py
python -m http.server 8000
```

Then open `http://localhost:8000/docs/`. To refresh only one scheduled stage, use `--ais-only` or `--sar-only`. / 然后打开 `http://localhost:8000/docs/`。如只刷新某个定时阶段，可使用 `--ais-only` 或 `--sar-only`。

Generate the daily report and, on Mondays, the weekly report:

```text
python src/generate_reports.py
```

## Check the project / 检查项目

```text
python -m compileall -q src
python -m unittest discover -s tests -v
python -c "import sys; sys.path.insert(0, 'src'); import generate_dashboard_data, generate_reports"
```

## Project layout / 项目结构

- `docs/` — GitHub Pages website and published JSON/GeoJSON/report files.
- `src/` — Python source adapters, scoring, event, and report pipeline.
- `data/reference/` — small human-readable reference lists.
- `data/processed/` — rolling AIS history and local processed snapshots.
- `data/events/events.csv` — append-only research-lead event ledger.
- `.github/workflows/update-data.yml` — scheduled and manual data automation.

## Disclaimer / 免责声明

Risk scores are review priorities, not legal or attribution determinations. SAR detections are leads for review, not confirmation of illicit activity. / 风险分数仅表示审查优先级，不构成法律或归因结论。SAR 探测仅为复核线索，并非对非法活动的确认。

Released under the [MIT License](https://opensource.org/license/mit).
