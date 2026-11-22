"""Local ML adapters: FFmpeg decoding, librosa analysis, CLAP embeddings."""

from .clap_embedder import (
    CLAP_EMBEDDING_DIMENSION,
    DEFAULT_CLAP_MODEL_ID,
    ClapAudioEmbedder,
)
from .ffmpeg_decoder import FFmpegAudioDecoder
from .hardware_probe import HardwareProbe
from .librosa_analyzer import LibrosaFeatureExtractor, analyze_pcm, fold_tempo

__all__ = [
    "CLAP_EMBEDDING_DIMENSION",
    "DEFAULT_CLAP_MODEL_ID",
    "ClapAudioEmbedder",
    "FFmpegAudioDecoder",
    "HardwareProbe",
    "LibrosaFeatureExtractor",
    "analyze_pcm",
    "fold_tempo",
]
