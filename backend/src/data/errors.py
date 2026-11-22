"""Data-layer exception types."""

from __future__ import annotations


class DataLayerError(Exception):
    """Base class for adapter failures."""


class ProviderError(DataLayerError):
    """A remote catalog/provider request failed."""


class ProviderRateLimitError(ProviderError):
    """A provider kept returning rate-limit responses after retries."""


class LLMError(DataLayerError):
    """The configured local LLM could not produce a usable response."""


class AudioPipelineError(DataLayerError):
    """Base class for audio decode/analysis failures."""


class FFmpegNotFoundError(AudioPipelineError):
    """No usable ``ffmpeg`` binary was found on this machine."""


class PreviewDownloadError(AudioPipelineError):
    """A preview URL could not be downloaded (404, timeout, retries exhausted)."""


class AudioDecodeError(AudioPipelineError):
    """FFmpeg failed or produced no usable PCM for the given audio payload."""


class EmbeddingError(DataLayerError):
    """The local embedding model could not produce a usable vector."""


class SetDownloadError(DataLayerError):
    """A DJ set could not be resolved or downloaded to disk."""


class FingerprintError(DataLayerError):
    """The audio fingerprint service could not complete a request."""
