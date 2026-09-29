# 影视拍摄连续性管理

项目使用 Python 标准库、SQLite 和 `http.server` 管理非线性拍摄中的连续性。场次与镜头分别记录叙事顺序和拍摄顺序，角色、服装、道具、伤痕状态按**全片叙事链**检查（跨场次衔接、未记录状态自动沿用），冲突可由调整方案或正式豁免处理，镜头只有在全片叙事链上无未处理冲突时才能锁定。

## 运行与测试

```bash
python app.py
python -m unittest discover -s tests -v
```

默认端口 `8115`，页面 <http://127.0.0.1:8115>。首次启动创建“雨夜追踪”示例：两个场次、拍摄顺序与叙事顺序相反，包含一个同场伤痕回退冲突和一个跨场次风衣状态变化冲突；第二场未记录的风衣/伤痕状态展示为沿用上一镜。数据库和端口可分别用 `CONTINUITY_DB`、`PORT` 指定。

## 连续性算法

全片镜头按「场次叙事顺序 → 场次内镜头叙事顺序」串成一条链，与拍摄顺序无关，逐镜向后接：

- 某镜对某元素**没有写新状态**时，沿用上一镜最近的一次人工/审批状态（`inherited`），沿用只用于比较与报告展示，**绝不写回数据库**，因此人工写下的值不会被覆盖。
- 每个元素选择一种规则：
  - `stable`：沿叙事顺序状态必须一致。
  - `monotonic`：使用 `numeric_value` 比较，数值不能下降，适合伤痕、污损或破坏程度。
  - `allowed`：只有预先登记的状态转移才能通过。
- 比较发生在相邻的两次显式状态之间，可跨越场次边界；跨场次冲突标记 `cross_scene=1`，归属到后一镜所在场次，单场操作仍能看到。

调整方案必须由制片人或场记提出、由另一位审片人批准；批准后写入镜头状态并对**全片**重新检查，报告与锁定结果一起更新。也可以为确实需要保留的冲突写入豁免理由（同样支持跨场次冲突）。锁定会再次对全片叙事链检查：归属本场的冲突、或以该镜为前一镜的跨场次冲突，豁免之外的活跃冲突都会阻止锁定；锁定后直接改状态会失败。

场次或镜头的叙事顺序变化后，冲突按「元素+前一镜+后一镜+类型」的指纹重新挂载：位置已经不存在的旧冲突自动置为失效（resolved），不会继续挂在错误位置；同一问题在新顺序下重现时复用原记录及其豁免结论。针对已失效冲突的待审调整方案不能再被批准。

## 主要接口

- `POST /api/users`、`POST /api/productions`
- `POST /api/productions/{id}/scenes`、`POST /api/scenes/{id}/shots`
- `POST /api/productions/{id}/elements`、`POST /api/elements/{id}/transitions`
- `POST /api/shots/{id}/states`、`POST /api/scenes/{id}/check`、`POST /api/productions/{id}/check`
- `POST /api/scenes/{id}/reorder`、`POST /api/shots/{id}/reorder`（调整叙事顺序，占用时交换，随后全片重检）
- `POST /api/conflicts/{id}/plans`、`POST /api/plans/{id}/review`
- `POST /api/conflicts/{id}/exemptions`
- `POST /api/shots/{id}/lock`
- `GET /api/productions/{id}/continuity`（含 `narrative_chain` 全片叙事链、逐镜显式/沿用状态、`cross_scene_conflicts`、逐场冲突）
- `GET /api/productions/{id}/conflicts?cross_scene=1`、`GET /api/scenes/{id}/conflicts?cross_scene=1`

页面顶部为**全片入口**：全片报告、跨场次冲突列表、叙事链表（人工/沿用状态分别标注）；单场与镜头的状态录入、单场复检、锁定、豁免、调整方案等操作保留在下方。
