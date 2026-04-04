# 角色视觉圣经 — 用户输入模板

请为以下角色生成视觉圣经（Character Visual Bible）。

## 角色基本信息

- **角色 ID**: {role_id}
- **显示名**: {canonical_name}

## 现有角色资料

### 身份摘要
{identity_summary}

### 显示摘要
{display_summary}

### 详细描述
{long_description}

### 故事功能
{story_function}

### 阶段弧线
{phase_arc}

### 所属势力
{power}

### 关系网络
{relationship_clusters}

### 重要转折点
{turning_points}

### 原文出处摘录
{source_excerpts}

## 要求
请严格按照系统指令中的 JSON schema 输出该角色的视觉圣经。确保：
1. `visual_hook` ≤ 20 字
2. `image_prompt_base` 为英文，50-80 词
3. `negative_constraints` 至少 2 条
4. `appearance_timeline` 至少 1 条初始阶段（`use_as_default_card = true`）
5. 所有外观描述忠于原文设定
