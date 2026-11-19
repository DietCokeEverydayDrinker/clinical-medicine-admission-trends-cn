# 研究纳入资格审计

更新日期：2026-11-19

## 审计目的

本审计检查分析面板是否对应“中国大陆普通本科临床医学专业”。招生表中
“临床医学”这一专业名称不足以确定专业层次。本科院校可以同时举办三年制
临床医学项目，专科院校也可能出现在名称看似本科批次的归档表中。专项计划、
定向就业、公费医学、民族班、预科和中外合作项目同样需要单列。

重建后的逐行字段保存在：

- [`output/clinical_eligibility_fields.csv`](output/clinical_eligibility_fields.csv)
- [`output/clinical_panel_2017_2026_eligibility_enriched.csv`](output/clinical_panel_2017_2026_eligibility_enriched.csv)

## 官方来源

### 普通高等学校名单

院校本科/专科层次来自教育部逐年《全国普通高等学校名单》。处理脚本使用
学校标识码跨年份追踪院校，避免更名造成身份断裂。2017 年新乡医学院三全学院
到豫北医学院的更名链即通过学校标识码完成匹配。

缓存文件、固定镜像提交、教育部原始页面和 SHA-256 均记录在
[`data/moe/moe_source_manifest.csv`](data/moe/moe_source_manifest.csv)。
目录结构与重建说明见 [`data/moe/README.md`](data/moe/README.md)。

### 高职专科临床医学备案

三年制临床医学项目来自教育部“高等职业教育专科专业设置备案结果查询”：

<https://zwfw.moe.gov.cn/zyyxzy/>

查询覆盖 2017–2026 年和 32 个省级及兵团辖区，共 320 个组合，得到
1,397 条学校年度专业备案记录。缓存响应保存在
[`data/moe/vocational_clinical/`](data/moe/vocational_clinical/)。

## 分类规则

`scripts/build_eligibility_fields.py` 综合以下证据：

1. 当年或最近可用的教育院校机构层次。
2. 招生表中的本科、专科或普通类分段批次。
3. 当年教育部三年制临床医学专业备案。
4. 有原始招生计划支撑的少量人工覆盖。

逐行分类结果如下：

| `program_degree_level` | 行数 | 含义 |
|---|---:|---|
| `undergraduate` | 35,395 | 可确认的本科专业记录 |
| `vocational_three_year` | 666 | 专科院校或三年制项目记录 |
| `ambiguous_dual_offer` | 298 | 本科院校同时备案三年制项目，投档表未给出专业层次 |
| `unresolved` | 507 | 院校无法可靠映射，主要来自“未标注院校” |

对无法从投档表区分本科与三年制项目的记录，当前保留
`ambiguous_dual_offer`，不从校名或分数硬猜。浙江“普通类第一段”同时包含
本科和部分专科项目，首都医科大学、重庆医科大学、新疆医科大学、齐鲁医药
学院等也确有三年制临床医学备案，因此这类模糊记录需要原始招生计划才能进
一步判定。

已确认的个案使用
[`data/manual_program_level_overrides.csv`](data/manual_program_level_overrides.csv)
保存学校、年份、结论、证据链接和说明。目前覆盖 2024 年山东省山东现代学院：
其普通专科招生计划明确列出临床医学、学制三年、计划 475 人。

## 招生口径

专业名和备注中的明确关键词用于区分：

| `admission_plan_type` | 行数 |
|---|---:|
| 普通常规 | 35,801 |
| 中外合作 | 353 |
| 定向就业 | 254 |
| 公费或免费医学 | 139 |
| 地方专项 | 76 |
| 国家专项 | 76 |
| 民族班 | 65 |
| 预科 | 60 |
| 高校专项 | 32 |
| 其他专项 | 10 |

国家专项、地方专项、高校专项、民族班、预科、定向就业、公费或免费医学等
项目不进入普通本科主候选。中外合作项目单列，主分析是否纳入由两位作者确认。

## 数量字段

来源中的数量字段含义并不统一。2026 年浙江官方表报告“计划数”，贵州报告
“投档数”，其余记录尚未全部核验。重建结果将原值保存在
`source_count_value`，并在 `count_definition` 中标记口径：

| `count_definition` | 行数 |
|---|---:|
| 来源未报告 | 28,789 |
| 已报告但口径待核验 | 7,684 |
| 计划数 | 215 |
| 投档数 | 178 |

当前主百分位指标不使用 `source_count_value` 加权，因此该字段的口径差异不会
直接改变现有百分位算法。任何招生规模加权、计划完成率或录取概率分析都必须
先完成字段口径核验。

## 2025–2026 官方端点重建

六个省级单位在 2025 和 2026 两端均可取得官方专业级投档表。直接附件、文件
大小和 SHA-256 记录在
[`data/official_endpoints/source_manifest.csv`](data/official_endpoints/source_manifest.csv)，
下载与解析命令见同目录 README。

重建脚本从完整专业池计算 `admission_percentile`，然后输出临床医学子集：

- [`clinical_official_endpoints_2025_2026.csv`](output/official_endpoints/clinical_official_endpoints_2025_2026.csv)
- [`official_endpoint_parse_summary.json`](output/official_endpoints/official_endpoint_parse_summary.json)
- [`official_endpoint_validation.json`](output/official_endpoints/official_endpoint_validation.json)

山东、河北、辽宁、浙江的 2026 官方解析与当前面板行数一致，百分位差异均在
舍入范围内。贵州 2026 的官方 PDF 包含 1–18,973 的连续唯一序号，其中 80 条
没有正的最低分或位次；可用于百分位的记录为 18,893 条，识别到 189 条临床医学
记录，而当前面板为 178 条。重庆 2025 官方表识别 171 条临床记录，当前面板为
172 条；2026 官方表识别 183 条，当前面板为 180 条，并遗漏 242 条使用字母
数字院校代码的合法记录。

因此，“2026 来源为官方”记录的是提供方，并不自动等于完整专业池已经进入
面板。面向全国原创 Article 的升级需要重建贵州和重庆 2026 端点，而不是只追加
2025 附件。

### 端点行数差的逐项核对

[`scripts/build_official_endpoint_reconciliation.py`](scripts/build_official_endpoint_reconciliation.py)
对上述三处差异做一对一行级匹配，并写出
[`official_endpoint_panel_reconciliation.csv`](output/official_endpoints/official_endpoint_panel_reconciliation.csv)
及对应 JSON 汇总。三处比较都使用“普通类本科批”：

| 来源 | 官方行 | 面板行 | 差值 | 行级结论 |
|---|---:|---:|---:|---|
| 重庆 2025 | 171 | 172 | −1 | 面板多 1 条中外合作重复：同一分数、位次和项目同时以重庆医科大学及联合学院名称出现 |
| 重庆 2026 | 183 | 180 | +3 | 官方多 3 条普通常规记录，均为字母数字院校代码；面板未保留 |
| 贵州 2026 | 189 | 178 | +11 | 官方多 10 条普通常规和 1 条国家专项记录 |

官方面板合计多出 14 条记录，其中 13 条为普通常规、1 条为国家专项；面板
另有 1 条中外合作重复。贵州 2026 官方表的数量字段是投档数，重庆 2025 和
2026 官方表未报告数量字段。这 13 条普通常规漏行需要在未来“官方到官方”
升级时回接主候选；当前全国结果仍只描述已编译面板，不能把“2026 来源为
官方”解释为该来源的完整专业池已全部进入全国估计。

## 敏感性分析

[`scripts/build_eligibility_fields.py`](scripts/build_eligibility_fields.py)
在 30 个可比省级单位中重算省均变化。全部口径方向一致：

| 口径 | 纳入行数 | 专业池：全部/固定同校 | 考生分布：全部/固定同校 |
|---|---:|---:|---:|
| 当前面板 | 36,866 | −10.01 / −0.78 | −9.31 / −3.89 |
| 排除专项/单独口径 | 36,154 | −10.26 / −0.84 | −9.28 / −3.91 |
| 仅本科专业层次 | 35,395 | −10.15 / −0.81 | −9.64 / −3.89 |
| 普通本科主候选 | 34,484 | −10.34 / −0.84 | −9.55 / −3.90 |
| 主候选整行去重 | 33,650 | −10.34 / −0.84 | −9.55 / −3.90 |
| 主候选业务键去重 | 33,448 | −10.34 / −0.84 | −9.55 / −3.90 |
| 模糊记录全部按本科纳入的上界 | 34,771 | −10.31 / −0.83 | −9.49 / −3.91 |
| 普通本科并纳入中外合作 | 34,819 | −10.40 / −0.86 | −9.61 / −3.91 |

主候选排除专科、专项/分流、中外合作和模糊专业层次。将 298 条模糊记录全部
按本科纳入后，专业池省均变化为 −10.31，固定同校变化为 −0.83；考生分布
对应为 −9.49 和 −3.91。主候选存在 834 条整行重复和 1,036 条业务键重复，
去重后两个指标的省均变化均未改变。广泛下移的方向对专业层次和重复记录处理
不敏感；精确幅度仍取决于原始招生计划对模糊记录的最终判定。

## 全国主候选的逐省输出

[`scripts/analyze_national_primary.py`](scripts/analyze_national_primary.py)
把普通本科主候选的 2025→2026 比较导出为逐省表：

- [`analysis_national_primary_province_changes.csv`](output/analysis_national_primary_province_changes.csv)
  同时保留专业池、考生分布、全部可用院校、固定同校和来源切换。
- [`analysis_national_primary_summary.json`](output/analysis_national_primary_summary.json)
  记录 30 个可比省级单位的省等权汇总与方向计数。
- [`analysis_national_primary_sensitivity.csv`](output/analysis_national_primary_sensitivity.csv)
  汇总八个资格、重复和中外合作口径。

主候选在 2025→2026 的省等权结果为：专业池全部院校 −10.34、固定同校 −0.84，
考生分布全部院校 −9.55、固定同校 −3.90 个百分点。专业池全部院校有 29/30
个省级单位为负，固定同校为 18/30；考生分布相应为 29/30 和 28/30。固定同校的
专业池结果在二手来源两端省份接近零均值，说明学校构成和来源切换能够产生很大
的表观变化。全国结果只描述该观测框架中的投档位置，不能解释为考生总体效应。

## 自动验证

[`scripts/validate_eligibility_fields.py`](scripts/validate_eligibility_fields.py)
检查行数、唯一键、分类互斥、主候选公式、山东现代学院案例、敏感性方向和
汇总一致性。验证结果写入
[`output/clinical_eligibility_validation.json`](output/clinical_eligibility_validation.json)。

当前检查通过：

- 原始面板与资格重建面板均为 36,866 行。
- 2,819 个院校年度匹配无重复。
- 1,397 条高职备案无关键字段重复。
- 专业层次、招生计划类型和数量口径均落在预定义集合。
- 主候选只包含普通常规本科记录。
- 八个敏感性情形在两个指标中均保持负向变化。
- 全国主候选逐省表为 30 行，四个省等权均值与敏感性表一致。

## 尚未解决

- 298 条本科院校“双项目”记录缺少可链接到专业层次的原始招生计划。
- 507 条未解析记录主要来自“未标注院校”，不进入主候选。
- 7,684 条已报告数量记录的字段定义仍需在需要规模加权时逐来源核验。
- 主候选是否纳入中外合作项目需要两位作者最终确认。
