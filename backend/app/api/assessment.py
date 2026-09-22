from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient, get_owned_conversation
from app.db.models import Patient
from app.db.session import get_db
from app.providers.embeddings import EmbeddingProvider, get_embedding_provider
from app.providers.llm import LLMProvider, get_llm_provider
from app.providers.tts import TextToSpeechProvider, TTSError, get_tts_provider
from app.providers.vector_store import VectorStore, get_vector_store
from app.reasoning.evidence_package import build_evidence_package
from app.reasoning.schema import Assessment
from app.safety.engine import evaluate_safety, vitals_from_patient_state
from app.schemas.assessment import AssessmentRequest
from app.tts.speech import synthesize_validated_response
from app.validation.validator import get_validated_output

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.post("", response_model=Assessment)
async def create_assessment(
    payload: AssessmentRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> Assessment:
    """The first (and only) path in this codebase allowed to hand a client anything
    Assessment-shaped. Runs architecture.canonical_pipeline's
    STRUCTURED_PATIENT_STATE -> EVIDENCE_RETRIEVAL -> CLINICAL_REASONING ->
    DETERMINISTIC_SAFETY -> OUTPUT_VALIDATION -> TEXT_RESPONSE, using Phase 3/5/6/7/8/9's
    already-built (and previously internal-only) pieces. app/reasoning and app/safety remain
    otherwise unreachable from the API — this endpoint is the sole caller that's allowed to
    treat their output as user-facing, and only after it has been through
    get_validated_output() (architecture.bypass_forbidden).

    DETERMINISTIC_SAFETY now evaluates real vitals (Phase 9's `vitals` snapshot, translated to
    vital_rules.py's key vocabulary by vitals_from_patient_state) instead of always {} — closing
    the gap flagged when this endpoint was first wired up.

    Still-open gap: medication safety is not cross-checked against whatever this endpoint's own
    output proposes. Assessment.medication_information is free text (per output_schema), not a
    structured drug-name list, and no reliable extractor exists yet to turn "consider
    acetaminophen" into a MedicationDBProvider.lookup() call without guessing. Building one is
    future work, not attempted here — see docs/KNOWN_LIMITATIONS.md. check_medication_validation
    (Phase 8) still runs, but with no medication_findings to check against, it is currently a
    no-op in this endpoint specifically.
    """

    await get_owned_conversation(db, patient, payload.conversation_id)

    evidence_package = await build_evidence_package(db, patient, embedding_provider, vector_store)
    vitals = vitals_from_patient_state(evidence_package.patient_state.vitals)
    safety_evaluation = await evaluate_safety(db, patient_id=patient.id, vitals=vitals)

    return await get_validated_output(llm, evidence_package, safety_evaluation)


@router.post("/speech")
async def create_assessment_speech(
    payload: AssessmentRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
    tts: TextToSpeechProvider = Depends(get_tts_provider),
) -> Response:
    """Phase 11 — voice_pipeline.flow's VALIDATED_TEXT -> TTS -> SPEAKER, as a genuinely
    optional companion to `POST /assessment`, never a replacement for it
    (ux.accessibility.text_always_available). Runs the identical pipeline as `POST /assessment`
    and only ever hands TTS an Assessment that has actually been through
    get_validated_output() — see app/tts/speech.py's synthesize_validated_response, the sole
    function permitted to call TextToSpeechProvider.speak().

    A TTS-specific failure (engine unavailable, synthesis error) returns 503 TTS_ERROR rather
    than silent/empty audio — the caller (mobile app) is expected to already have, or separately
    fetch, the text via POST /assessment and simply not play audio on this failure; TTS is never
    the only response channel.
    """

    await get_owned_conversation(db, patient, payload.conversation_id)

    evidence_package = await build_evidence_package(db, patient, embedding_provider, vector_store)
    vitals = vitals_from_patient_state(evidence_package.patient_state.vitals)
    safety_evaluation = await evaluate_safety(db, patient_id=patient.id, vitals=vitals)

    try:
        _, audio = await synthesize_validated_response(tts, llm, evidence_package, safety_evaluation)
    except TTSError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"TTS_ERROR: {exc}") from exc

    return Response(content=audio, media_type="audio/wav")
