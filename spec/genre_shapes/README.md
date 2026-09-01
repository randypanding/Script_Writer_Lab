# 套路注册表 · spec/genre_shapes/
# 质量进攻 Q5(ADR-0004)的可执行资产——把"套路"参数化为机器可读形状,而非模板化

> 回答用户问题:"我有没有必要让项目里拥有特定的套路,然后按套路去走?"
> **结论:要,但必须参数化、科学化、不模板化。**
>
> - **参数化**:套路 = 一组可测量的形状(维度锚 + 张力曲线 + 钩型配额 + 结构约束),
>   不是一句"要打脸""要甜宠"的形容词。形状由 522 卡标注实测得出
>   (mined/craft_anchors_v2.json),不是拍脑袋。
> - **科学化**:同一部作品按题材对齐形状后,再用判官验证"对齐后是否真的更好"
>   (craft_bench 测量),而不是"我觉得像爆款了"。数据闭环,不靠感觉。
> - **不模板化**:形状是"节奏/强度的分布",不是"情节的复制"。同一个复仇锚,
>   可以长出复仇文、逆袭文、虐渣文、重生文——锚约束的是节奏与密度,不约束
>   事件内容。段落怎么写、对话怎么设计,仍是判官与范例引导的自由空间。

## 目录结构

```
spec/genre_shapes/
  shapes.yaml      ← 机读形状(由 mined/craft_anchors_v2.json 生成,单一事实源)
  README.md        ← 本文件(哲学 + 用法 + 扩展约定)
```

## shapes.yaml 字段说明

- `weights`:五维权重(hook .25 / person .25 / info_gap .20 / cliffRD .15 / turn .15)。
  判官评估 craft 形状贴合度时,按此权重聚合。
- `shapes.<题材>.anchor`:五维锚值(0-1)——该题材头部作品的工艺密度中位。
- `shapes.<题材>.tension_curve`:前/中/后三段张力均值(1-5)。形状 = 曲线,不只 = 数值。
- `shapes.<题材>.provisional`:true 表示薄锚(样本不足,如治愈成长 1 部 15 卡),
  只作方向参考,不据此加压。
- `shapes.<题材>.keywords`:题材检测关键词(与 SW craft_shape.yaml detect 一致)。

## 与 SW craft_shape.yaml 的关系

- Lab 的 `shapes.yaml` 是**证据源**(锚 + 曲线,来自 522 卡)。
- SW 的 `spec/craft_shape.yaml` 是**消费侧**(把锚翻译成 nsc 可执行的形状:
  antagonist_required / hook_types / stakes_escalation / arousal_peak / ending_beats)。
- 规则:Lab 改锚(补料重标)→ 触发 SW craft_shape 同步更新(对 SW 的 PR + ADR)。
  现有 SW craft_shape 只映射了 爆款通用 / 治愈成长 两个形状;六桶全量映射是
  Q5 的执行子项(ADR-0004)。

## 判官如何消费形状(Q5 落地)

1. 判官评估某章时,先按 brief 检测题材 → 取 shapes.<genre>.anchor。
2. 计算"形状贴合度"= 该章五维实测与锚的加权距离(反向)。
3. 贴合度进 craft_bench 或单独的形状分——高冲突题材(复仇/甜宠)锚值高,
   治愈系锚值低;同一章在复仇锚下可能是"冲突不足",在治愈锚下可能是"过冲"。
4. 这解决混题材锚失真问题(round25 实证:R4 为拉 person 把 transportation 打破地板)。

## 扩展约定

- **新题材**:先在 Lab 补锚(≥8 部作品或标注 provisional),再映射 SW craft_shape。
- **改锚**:改 mined/craft_anchors_v2.json(契约冻结,改锚=改合同=重刻基线),
  重跑 scripts/compute_anchors.py 再生成 shapes.yaml——禁止手改 shapes.yaml。
- **套路不是模板**:形状卡只约束"节奏与强度分布",不约束"事件内容"。
  任何试图把形状卡变成"情节公式"的用法都是对这套设计的误用。
