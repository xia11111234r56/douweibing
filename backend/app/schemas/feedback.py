from typing import Literal

from pydantic import BaseModel, Field, model_validator

# 严重度纠正取值（与识别严重度口径一致：轻/中/重）。健康 = 无病害，不适用。
SEVERITY_VALUES = ("轻度", "中度", "重度")


class FeedbackCreate(BaseModel):
    """识别纠错反馈提交体。识别错误(is_correct=False)时必须给出正确病害。"""

    is_correct: bool = Field(True, description="识别结果是否正确")
    corrected_disease_id: int | None = Field(
        None, description="正确病害 id（识别错误时必填）"
    )
    corrected_severity: Literal["轻度", "中度", "重度"] | None = Field(
        None, description="纠正后的严重度（健康时后端强制置空）"
    )
    remark: str | None = Field(None, max_length=500, description="备注")

    @model_validator(mode="after")
    def _require_corrected_when_wrong(self):
        if self.is_correct is False and self.corrected_disease_id is None:
            raise ValueError("识别错误时必须提供 corrected_disease_id")
        return self


class FeedbackOut(BaseModel):
    """反馈记录视图（含预测/正确病害名称，供管理平台展示）。"""

    id: int
    recognition_id: int
    user_id: int | None = None
    is_correct: bool
    corrected_disease_id: int | None = None
    corrected_name: str | None = None
    corrected_severity: str | None = None
    predicted_name: str | None = None
    remark: str | None = None
    created_at: str | None = None


class FeedbackPage(BaseModel):
    items: list[FeedbackOut]
    total: int
