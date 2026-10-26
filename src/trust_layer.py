import os
import re
import nltk
from sentence_transformers import CrossEncoder

# The punkt_tab tokenizer is baked into the Docker image at build time. Outside the image, try a
# quiet one-off download; if that is impossible (air-gapped host) fall back to a regex splitter
# instead of failing every verification request.
_PUNKT_AVAILABLE = True
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    try:
        _PUNKT_AVAILABLE = bool(nltk.download('punkt_tab', quiet=True, raise_on_error=True))
    except Exception:
        _PUNKT_AVAILABLE = False


def split_claims(text: str) -> list[str]:
    """Split an answer into sentence-level claims (NLTK punkt, regex fallback)."""
    if _PUNKT_AVAILABLE:
        try:
            return [s for s in nltk.tokenize.sent_tokenize(text) if s.strip()]
        except LookupError:
            pass
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [p.strip() for p in parts if p.strip()]

# Initialize the CrossEncoder globally so it's loaded only once
# We use nli-deberta-v3-small for local, 100% offline NLI fact-checking.
VERIFIER_MODEL_NAME = 'cross-encoder/nli-deberta-v3-small'

_verifier_model = None

def get_verifier():
    global _verifier_model
    if _verifier_model is None:
        # Initializing the model will download it to HF cache if it's not present.
        # Once downloaded, it runs 100% offline.
        _verifier_model = CrossEncoder(VERIFIER_MODEL_NAME)
    return _verifier_model

def verify_claims(draft_answer, context_texts):
    """
    Splits the draft answer into claims, verifies each against the combined context,
    and returns a reliability score along with the annotated claims.
    """
    if not draft_answer or not context_texts:
        return {
            "score": 100,
            "claims": [{"text": draft_answer, "status": "neutral"}]
        }
    
    # Combine context into a single string
    # Cross encoders truncate internally based on their max_length (usually 512)
    combined_context = " ".join(context_texts)
    
    # 1. Extract claims using NLTK
    claims = split_claims(draft_answer)
    if not claims:
        return {"score": 100, "claims": []}
    
    # 2. Verify each claim
    model = get_verifier()
    pairs = [[combined_context, claim] for claim in claims]
    
    # The model outputs logits for [Contradiction, Entailment, Neutral]
    scores = model.predict(pairs)
    
    results = []
    supported = 0
    contradicted = 0
    neutral = 0
    
    for i, claim in enumerate(claims):
        claim_scores = scores[i]
        # label mapping for cross-encoder/nli-deberta-v3-small:
        # 0: contradiction, 1: entailment, 2: neutral
        import numpy as np
        pred_label_idx = np.argmax(claim_scores)
        
        # Fast-path: If the claim is just a direct substring extraction (ignoring case),
        # it is definitionally entailed by the text. NLI models often fail on short, non-sentence phrases.
        # We require at least 5 characters to avoid matching single stray letters (like "F").
        if len(claim.strip()) > 5 and claim.lower().strip() in combined_context.lower():
            status = "entailment"
            supported += 1
        elif pred_label_idx == 1:
            status = "entailment"
            supported += 1
        elif pred_label_idx == 0:
            status = "contradiction"
            contradicted += 1
        else:
            status = "neutral"
            neutral += 1
            
        results.append({
            "text": claim,
            "status": status
        })
        
    # 3. Calculate Reliability Score
    total = len(claims)
    if total == 0:
        score = 100
    else:
        # Math: Every supported claim adds 1. 
        # Every contradiction subtracts 1.5. 
        # Every neutral subtracts 0.5.
        raw_score = (supported - (contradicted * 1.5) - (neutral * 0.5)) / total
        # Map raw_score from -1.5 to 1.0 into 0% to 100% roughly, or just max(0, min(100, raw_score * 100))
        # If all supported, score = 1.0 (100%)
        # If all neutral, score = -0.5 (0%)
        score_percent = max(0, min(100, int(raw_score * 100)))
        
    return {
        "score": score_percent,
        "claims": results
    }
