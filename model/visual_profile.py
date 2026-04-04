"""Pydantic models for Character Visual Profiles (角色形象档案).

These models describe the visual profile for characters — structured descriptions
designed for image generation, storyboarding, and the homepage Databank-style
character cards.  They live alongside (not inside) the existing entity_profiles
and unified_knowledge data.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class AppearanceDetails(BaseModel):
    """Structured visual description for a character's default appearance."""

    age_and_build: str = Field(
        description="年龄段与体态，例如'少年、瘦削偏矮'或'中年、魁梧'"
    )
    facial_features: str = Field(
        description="脸部特征，如轮廓、眉眼、皮肤色调"
    )
    hair: str = Field(
        description="发型与发色"
    )
    clothing_and_materials: str = Field(
        description="服饰与面料/材质（粗布、铁甲、道袍等）"
    )
    color_palette: str = Field(
        description="角色整体配色方向"
    )
    signature_items: str = Field(
        default="",
        description="标志性器物或配件"
    )
    aura_and_camera_feel: str = Field(
        description="气质与镜头感觉，例如'沉稳内敛、特写长焦'或'飘逸、逆光侧影'"
    )


class AppearanceTimelineEntry(BaseModel):
    """A single phase in a character's visual evolution."""

    phase_label: str = Field(
        description="阶段标签，例如'泥瓶巷少年'、'剑气长城修行期'"
    )
    range_hint: str = Field(
        description="大致章节/卷范围提示，例如'第一卷至第三卷'"
    )
    change_summary: str = Field(
        description="本阶段相对初始形象的变化摘要"
    )
    visual_delta: str = Field(
        description="视觉层面具体变化，可供图片模型参考"
    )
    use_as_default_card: bool = Field(
        default=False,
        description="是否作为首页卡图的默认阶段（通常只有初始阶段为 true）"
    )


class CharacterVisualProfile(BaseModel):
    """Complete visual bible entry for a single character."""

    role_id: str = Field(description="角色 ID，与 KB 一致")
    canonical_name: str = Field(description="显示名")
    card_title: str = Field(description="首页卡片标题（通常同 canonical_name）")
    visual_hook: str = Field(
        description="一句视觉钩子，用于首页卡片短句，≤20 字"
    )
    initial_appearance: str = Field(
        description="首页卡默认使用的初始形象总述"
    )
    appearance_details: AppearanceDetails = Field(
        description="结构化视觉说明"
    )
    negative_constraints: List[str] = Field(
        default_factory=list,
        description="禁止误生成的点列表"
    )
    image_prompt_base: str = Field(
        description="供图像生成模型直接使用的基础英文提示词"
    )
    image_style_notes: str = Field(
        default="写实倾向、影视概念设定感、非二游模板、非网文封面夸饰。同一套镜头语言和材质系统。前现代汉语奇幻世界，所有材质和工艺必须符合古代水平。",
        description="首页卡图统一风格约束"
    )
    appearance_timeline: List[AppearanceTimelineEntry] = Field(
        default_factory=list,
        description="阶段性外观变化记录"
    )


class CharacterVisualProfilesPayload(BaseModel):
    """Top-level container for the character_visual_profiles.json file."""

    version: str = Field(default="character-visual-profiles-v1")
    generated_at: str = Field(default="")
    generator: str = Field(default="gemini-api")
    model: str = Field(default="")
    roster_version: str = Field(default="high-value-roster-v1")
    profiles: List[CharacterVisualProfile] = Field(default_factory=list)
