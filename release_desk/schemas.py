"""The shapes that pass between the steps of a review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- extraction


class Cited(BaseModel):
    """A value read from a document, with the line it was read from."""

    value: str | None = Field(None, description="The value exactly as written, or null if blank or absent")
    line: int | None = Field(None, description="Line number (from the L-prefix) where the value appears")
    quote: str | None = Field(None, description="A short verbatim excerpt of that line containing the value")


class TestResult(BaseModel):
    key: str = Field(description="One of the test keys given in the instructions")
    result: Cited


class Step(BaseModel):
    step: int
    operation: str
    performed_by: Cited
    verified_by: Cited


class Deviation(BaseModel):
    id: str
    title: str
    status: Cited


class CertificateExtract(BaseModel):
    lot_id: Cited
    product_code: Cited
    manufacture_date: Cited
    expiry: Cited
    spec_revision: Cited = Field(default_factory=Cited, description="The specification revision the certificate says it tested against, e.g. '04'")
    approved_by: Cited
    results: list[TestResult]


class BatchRecordExtract(BaseModel):
    lot_id: Cited
    product_code: Cited
    manufacture_date: Cited
    line_clearance_by: Cited
    yield_percent: Cited
    steps: list[Step]


class DeviationLogExtract(BaseModel):
    lot_id: Cited
    deviations: list[Deviation]


class LotExtraction(BaseModel):
    certificate: CertificateExtract
    batch_record: BatchRecordExtract
    deviation_log: DeviationLogExtract


# ------------------------------------------------------------------ checking

Severity = Literal["critical", "major", "minor"]
BLOCKING: set[str] = {"critical", "major"}


class Evidence(BaseModel):
    document: str
    line: int | None
    text: str | None


class Finding(BaseModel):
    id: str
    rule: str
    severity: Severity
    title: str
    expected: str
    observed: str
    evidence: list[Evidence] = []


class EvidenceNote(BaseModel):
    """Raised when the model cited something the document does not say."""

    field: str
    document: str
    claimed_value: str | None
    cited_line: int | None
    reason: str


# ------------------------------------------------------------ investigation

NextStep = Literal[
    "reassess_with_corrected_document",
    "request_corrected_document",
    "route_to_deviation_owner",
    "confirm_with_laboratory",
    "request_missing_evidence",
    "no_further_evidence_needed",
]


class EvidenceRef(BaseModel):
    document: str
    line: int | None = None


class InvestigationNote(BaseModel):
    """What the investigator found. Advice to the reviewer; it changes no finding."""

    finding_ids: list[str] = Field(description="The findings this note is about")
    summary: str = Field(description="Two or three plain sentences: what the evidence shows")
    evidence: list[EvidenceRef] = Field(default_factory=list)
    next_step: NextStep
    open_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- proposals


class SecondReading(BaseModel):
    agrees: bool = Field(description="True if the proposal follows from the findings")
    concerns: list[str] = Field(default_factory=list, description="Short, specific concerns, if any")


Proposal = Literal["release", "hold", "none"]
