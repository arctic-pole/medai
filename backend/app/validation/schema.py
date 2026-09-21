from pydantic import BaseModel, Field


class ValidationFailure(BaseModel):
    check: str  # one of output_validator.checks' 10 names
    detail: str


class ValidationResult(BaseModel):
    passed: bool
    failures: list[ValidationFailure] = Field(default_factory=list)
