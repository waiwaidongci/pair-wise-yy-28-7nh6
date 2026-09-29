# 影视拍摄连续性管理

项目使用 Python 标准库、SQLite 和 `http.server` 管理非线性拍摄中的连续性。场次与镜头分别记录叙事顺序和拍摄顺序，角色、服装、道具、伤痕状态按**全片叙事链**检查：每场镜头按各自叙事顺序接在前一场之后，元素在某镜头没有写入新状态时沿用上一镜最近状态（沿用只用于检测与报告，不写回镜头，人工写下的值不会被覆盖）。冲突可由调整方案或正式豁免处理，镜头只有在无未处理冲突时才能锁定。

## 运行与测试

```bash
python app.py
python -m unittest discover -s tests -v
```

默认端口 `8115`，页面 <http://127.0.0.1:8115>。首次启动创建“雨夜追踪”示例，其中拍摄顺序与叙事顺序相反，并生成一个场内伤痕回退冲突和一个跨场次服装冲突。数据库和端口可分别用 `CONTINUITY_DB`、`PORT` 指定。

## 连续性算法

每个元素选择一种规则：

- `stable`：沿叙事顺序状态必须一致。
- `monotonic`：使用 `numeric_value` 比较，数值不能下降，适合伤痕、污损或破坏程度。
- `allowed`：只有预先登记的状态转移才能通过。

检测沿全片叙事链执行（场次按叙事顺序、场内镜头按各自叙事顺序串接），与剪辑和拍摄顺序无关；相邻镜头分属不同场次时即跨场次冲突，报告中以 `cross_scene` 标记。调整方案必须由制片人或场记提出、由另一位审片人批准；批准后写入镜头状态并重新检查，报告与锁定结果随之一起更新。也可以为确实需要保留的冲突写入豁免理由。锁定会再次检查场次，豁免之外的活跃冲突会阻止锁定，锁定后直接改状态会失败。

## 顺序调整

`POST /api/scenes/{id}/reorder`、`POST /api/shots/{id}/reorder` 调整场次或镜头的叙事顺序，目标位置被占用时与其交换。调整后立即按新顺序重算全片冲突：不再成立的旧冲突标记为已解决，不会继续挂在错误位置；新出现的冲突按新位置生成。

## 主要接口

- `POST /api/users`、`POST /api/productions`
- `POST /api/productions/{id}/scenes`、`POST /api/scenes/{id}/shots`
- `POST /api/productions/{id}/elements`、`POST /api/elements/{id}/transitions`
- `POST /api/shots/{id}/states`
- `POST /api/productions/{id}/check`（全片检查）、`POST /api/scenes/{id}/check`（单场检查）
- `POST /api/scenes/{id}/reorder`、`POST /api/shots/{id}/reorder`
- `POST /api/conflicts/{id}/plans`、`POST /api/plans/{id}/review`
- `POST /api/conflicts/{id}/exemptions`
- `POST /api/shots/{id}/lock`
- `GET /api/productions/{id}/continuity`（含全片叙事链 `film_chain` 与跨场次冲突）、`GET /api/productions/{id}/conflicts`
