# 双门槛换档核账

质控班使用两档规程 `L`、`H`，值域为 `[0,2] μm`。P 批的 L 档读到 2、H 档读到 0，每条权重为 2。Q 批在每档各读到 0 和 2，每条权重为 1。分别冻结发行，关闭源库后对两个固定件提交相同的门槛 1、2。

两件的最优损失都应为 4，各档的逐档范围都应为 `[0,2]`。按档位位置核对，P 的报告应为 `(1,1)`、`(1,null)`、`(null,null)`。Q 的报告应为 `(1,1)`、`(1,2)`、`(1,null)`、`(2,2)`、`(2,null)`、`(null,null)`。曲线 `(1,2)` 只在 Q 的最优集中。两份报告都须绑定实际采用的固定标定件。

故障版的 P 多签了 `(1,2)`、`(2,2)` 和 `(2,null)`。原断言同时核对固定件的曲线成员判定和停源后的签报结果。

```sh
python3 -B -m unittest -v tests.test_calibration.CalibrationTests.test_same_marginals_retain_joint_evidence tests.test_switching.SwitchingTests.test_offline_accident_pair
```

运行清单 `.pointwise-runtime.json` 中的 `verify` 和 `demo` 都是执行参数数组，分别运行全套原回归和日常更正交班演示。`setup` 是准备命令列表，本工程为空。沿用清单现有版本、类型和入口。修复后，事故核账、全套回归和日常演示均应通过。
