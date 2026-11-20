# 临湾涂层计量室

计量员按厚度规程录入仪器纸面读数。复核员更正误录并冻结确切修订，标定岗发行固定标定件。夜班用工艺单上的两项门槛签出可行换档表，次日档案岗按号核对结论及实际采用的标定。数据保存在独立的源库与档案库。签报和历史领取只需档案库。

## 运行

需要 Python 3.11 与标准库。平台物化工程时提供 `check_project.py`，由它发现 `tests` 包中的完整套件。

```sh
python3 -B check_project.py
python3 -B demo.py
```

演示在独立临时目录运行。先录入两档均为 2 μm 的读数，冻结、发行，关闭源库后用门槛 1、2 签报。然后重开源库把首档更正为 0，重新冻结发行，再关闭源库签报。两件的最优损失均为 0，先后报告的首达对分别为 `(1, 1)` 和 `(2, 2)`。演示重开档案库，核对两份原报告、各自父件、冻结来源和回执后输出一行 JSON。

## Python 接口

| 入口 | 输入与结果 |
| --- | --- |
| `measurements.repository.MeasurementRepository.open(path)` | 打开源库。调用 `initialize()` 建表。用 `close()` 关闭。规程函数使用 `repo.connection`。 |
| `protocol.registry.register_protocol(connection, protocol_id, levels, unit, lower, upper)` | 追加规程版本，返回 `ProtocolRule`。用其 `version_id` 指定规程。同一规程号可以登记多个版本。 |
| `measurements.intake.submit_reading(repo, batch_id, protocol_version, original_id, level, value, weight, *, corrects=None)` | 接纳一条测次或更正，返回 `AcceptedReading`，其 `revision_id` 可用于更正或冻结。首条测次可建立批次，也可用 `repo.begin_batch(batch_id, protocol_version)` 先建空批次。 |
| `measurements.freeze.freeze_revision(repo, batch_id, protocol_version, revision_ids=None)` | 固定明确给出的修订选择，省略选择时固定批次的当前队列。返回 `FrozenBatch`。用 `load_frozen_batch(repo, frozen_id)` 重读确切来源。 |
| `archive.storage.open_archive(path)` 与 `initialize_archive(connection)` | 打开并初始化档案库。调用方负责关闭连接。档案号在同一档案库中分配，规程版本、修订号及冻结号在配套源库中分配。 |
| `calibration.issue.issue_calibration(repo, archive, frozen_id)` | 发行指定冻结号。返回带 `artifact_id`、`payload` 和 `receipt` 的 `PublishedArtifact`。正文含单位、档位顺序、最优损失、逐档范围及完整最优证据。 |
| `switching.report.publish_switch_report(archive, calibration_id, low, high)` | 从指定已发布标定件签报，返回带 `artifact_id`、`parent_id`、`pairs` 和 `receipt` 的 `SwitchReport`。 |
| `archive.retrieval.read_artifact(archive, artifact_id)` | 返回 `ArtifactReadResult`。`found` 提供 `record`、`parent_chain` 与 `receipt`。未知号返回 `not_found`。`record.body` 是保存的原 JSON 正文，`record.payload` 提供解码视图。 |

规程包含 2 至 8 个唯一档位，顺序以登记为准。允许单位 `nm`、`μm` 和 `mm`。读数、值域和门槛接受整数、`Fraction` 或精确的数字字符串，如 `1/3`。值域是可退化为一点的闭区间，读数和门槛可落在区间之外。测次权重须为正整数。不同原测次号的重复读数分别计权。更正追加修订并更新当前队列，同一原测次的历史修订仍可被明确选入冻结件。冻结选择非空且每个原测次只出现一次。

标定值按档位非降，在规程值域内最小化读数的加权绝对偏差。缺测档的局部损失为零。逐档范围是全体最优曲线的投影。可用 `calibration.certificate.decode_certificate(payload).contains_curve(values)` 核对一条有序曲线能否达到固定件的最优损失。固定件保留数学约束和批次级来源，逐测次标识与读数保存在源库。

两个门槛须严格递增。达到包含等号，首达前严格低于门槛。结果用规程中从 1 开始的位置表示档位，用 Python `None` 或 JSON `null` 表示全程未达。报告按低门槛首达位置、高门槛首达位置排序，未达在末尾。每对必须由同一条最优曲线实现。

非法数据或签报请求抛出 `ValueError`，未知规程或冻结号抛出 `LookupError`。提交错误由 SQLite 抛出，事务撤销成果及回执。重复初始化保留已录资料和已发布成果。领取按保存的父引用追溯到冻结号，即使源库关闭也能核档。
