"""Lens pure-logic package — L3 "read-out" primitives.

Pure, I/O-free helpers for the cross-idea contradiction detector (Lens 第一刀):
salient topic-term extraction and lexical candidate prefiltering. No external
NLP deps, no embeddings, no persistent Lens store — these are deterministic
functions the LensService composes at grill time.
"""

from anneal.lens.prefilter import prefilter_candidates
from anneal.lens.topic_terms import topic_terms

__all__ = ["topic_terms", "prefilter_candidates"]
