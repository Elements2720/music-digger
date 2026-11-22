from __future__ import annotations

import dataclasses
import math

import pytest

from domain.value_objects.audio_features import EmbeddingVector


def test_embedding_vector_accepts_tuple_and_list() -> None:
    from_tuple = EmbeddingVector((1.0, 2.0, 3.0))
    from_list = EmbeddingVector([1.0, 2.0, 3.0])  # type: ignore[arg-type]
    assert from_tuple.values == (1.0, 2.0, 3.0)
    assert from_list == from_tuple
    assert isinstance(from_tuple.values, tuple)


def test_embedding_vector_normalizes_numeric_values_to_float() -> None:
    vector = EmbeddingVector((1, 2, 3))  # type: ignore[arg-type]
    assert vector.values == (1.0, 2.0, 3.0)
    assert all(isinstance(value, float) for value in vector.values)


def test_embedding_vector_dimension_and_len() -> None:
    vector = EmbeddingVector((1.0, 2.0, 3.0, 4.0))
    assert vector.dimension == 4
    assert len(vector) == 4


def test_embedding_vector_accepts_explicit_matching_dimension() -> None:
    vector = EmbeddingVector(values=(1.0, 2.0, 3.0), dimension=3)
    assert vector.dimension == 3
    assert vector == EmbeddingVector((1.0, 2.0, 3.0))


@pytest.mark.parametrize("dimension", [2, 4, 0, -1])
def test_embedding_vector_rejects_mismatched_or_invalid_dimension(
    dimension: int,
) -> None:
    with pytest.raises(ValueError, match="dimension"):
        EmbeddingVector(values=(1.0, 2.0, 3.0), dimension=dimension)


@pytest.mark.parametrize("dimension", [True, 3.0, "3"])
def test_embedding_vector_rejects_non_integer_dimension(dimension: object) -> None:
    with pytest.raises(TypeError, match="dimension"):
        EmbeddingVector(values=(1.0, 2.0, 3.0), dimension=dimension)  # type: ignore[arg-type]


@pytest.mark.parametrize("values", [(), []])
def test_embedding_vector_rejects_empty_vectors(values: object) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        EmbeddingVector(values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "values",
    [
        (1.0, math.nan),
        (1.0, math.inf),
        (1.0, -math.inf),
        (1.0, "2.0"),
        (1.0, None),
        (1.0, True),
    ],
)
def test_embedding_vector_rejects_invalid_components(values: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        EmbeddingVector(values)  # type: ignore[arg-type]


@pytest.mark.parametrize("values", ["abc", b"abc", bytearray(b"abc"), 42])
def test_embedding_vector_rejects_non_iterable_or_string_values(values: object) -> None:
    with pytest.raises(TypeError):
        EmbeddingVector(values)  # type: ignore[arg-type]


def test_embedding_vector_is_immutable() -> None:
    vector = EmbeddingVector((1.0, 2.0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        vector.values = (3.0, 4.0)  # type: ignore[misc]


def test_embedding_vector_is_hashable() -> None:
    assert hash(EmbeddingVector((1.0, 2.0))) == hash(EmbeddingVector((1.0, 2.0)))
    assert len({EmbeddingVector((1.0, 2.0)), EmbeddingVector((1.0, 2.0))}) == 1


def test_validate_dimension_accepts_expected_width() -> None:
    EmbeddingVector((1.0, 2.0, 3.0)).validate_dimension(3)


def test_validate_dimension_rejects_mismatch_and_bad_arguments() -> None:
    vector = EmbeddingVector((1.0, 2.0, 3.0))
    with pytest.raises(ValueError, match="dimension mismatch"):
        vector.validate_dimension(4)
    with pytest.raises(ValueError, match="positive"):
        vector.validate_dimension(0)
    with pytest.raises(TypeError):
        vector.validate_dimension("3")  # type: ignore[arg-type]


def test_from_sequence_validates_optional_dimension() -> None:
    vector = EmbeddingVector.from_sequence([1.0, 2.0], expected_dimension=2)
    assert vector.dimension == 2
    with pytest.raises(ValueError, match="dimension mismatch"):
        EmbeddingVector.from_sequence([1.0, 2.0], expected_dimension=3)


def test_cosine_similarity_of_identical_vectors_is_one() -> None:
    vector = EmbeddingVector((1.0, 2.0, 3.0))
    assert vector.cosine_similarity(vector) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero() -> None:
    assert EmbeddingVector((1.0, 0.0)).cosine_similarity(
        EmbeddingVector((0.0, 1.0))
    ) == pytest.approx(0.0)


def test_cosine_similarity_of_opposite_vectors_is_minus_one() -> None:
    assert EmbeddingVector((1.0, 2.0)).cosine_similarity(
        EmbeddingVector((-1.0, -2.0))
    ) == pytest.approx(-1.0)


def test_cosine_similarity_known_value() -> None:
    left = EmbeddingVector((1.0, 2.0, 3.0))
    right = EmbeddingVector((4.0, 5.0, 6.0))
    expected = 32.0 / (math.sqrt(14.0) * math.sqrt(77.0))
    assert left.cosine_similarity(right) == pytest.approx(expected)


def test_cosine_similarity_is_symmetric() -> None:
    left = EmbeddingVector((1.0, 2.0, 3.0))
    right = EmbeddingVector((4.0, -5.0, 6.0))
    assert left.cosine_similarity(right) == pytest.approx(right.cosine_similarity(left))


def test_cosine_similarity_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="different dimensions"):
        EmbeddingVector((1.0, 2.0)).cosine_similarity(EmbeddingVector((1.0, 2.0, 3.0)))


def test_cosine_similarity_rejects_zero_vectors() -> None:
    with pytest.raises(ValueError, match="zero vector"):
        EmbeddingVector((0.0, 0.0)).cosine_similarity(EmbeddingVector((1.0, 0.0)))


def test_cosine_similarity_rejects_non_vector() -> None:
    with pytest.raises(TypeError, match="other must be an EmbeddingVector"):
        EmbeddingVector((1.0, 2.0)).cosine_similarity((1.0, 2.0))  # type: ignore[arg-type]
