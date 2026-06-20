"""Comprehensive test suite for quantum error correction module.

Tests cover:
- Valid quantum state initialization
- Error detection and correction
- Encoding and decoding
- Syndrome measurements
- Exception handling
- Observable metrics
"""

import pytest
from quantum_ecc import (
    QuantumBit,
    QuantumErrorCorrection,
    QuantumState,
    SyndromeResult,
    QuantumMetrics,
    InvalidQuantumStateError,
    EncodingError,
    CorrectionError,
    DecodingError,
    DepolarizingError,
)


class TestQuantumBit:
    """Test cases for QuantumBit class."""

    def test_valid_state_zero(self) -> None:
        """Test creation with valid '0' state."""
        qbit = QuantumBit('0')
        assert qbit.state == QuantumState.ZERO
        assert not qbit.is_encoded
        assert qbit.error_history == []

    def test_valid_state_one(self) -> None:
        """Test creation with valid '1' state."""
        qbit = QuantumBit('1')
        assert qbit.state == QuantumState.ONE

    def test_valid_state_plus(self) -> None:
        """Test creation with valid '+' state."""
        qbit = QuantumBit('+')
        assert qbit.state == QuantumState.PLUS

    def test_valid_state_minus(self) -> None:
        """Test creation with valid '-' state."""
        qbit = QuantumBit('-')
        assert qbit.state == QuantumState.MINUS

    def test_invalid_state_raises_error(self) -> None:
        """Test that invalid state raises InvalidQuantumStateError."""
        with pytest.raises(InvalidQuantumStateError) as exc_info:
            QuantumBit('invalid')
        assert "Invalid quantum state" in str(exc_info.value)

    def test_invalid_state_none_raises_error(self) -> None:
        """Test that None state raises InvalidQuantumStateError."""
        with pytest.raises(InvalidQuantumStateError):
            QuantumBit(None)  # type: ignore

    def test_error_recording(self) -> None:
        """Test that errors are recorded in history."""
        qbit = QuantumBit('0')
        qbit.record_error('bit_flip')
        qbit.record_error('phase_flip')
        assert qbit.error_history == ['bit_flip', 'phase_flip']

    def test_repr(self) -> None:
        """Test string representation."""
        qbit = QuantumBit('0')
        assert 'QuantumBit' in repr(qbit)
        assert 'state=0' in repr(qbit)


class TestQuantumErrorCorrection:
    """Test cases for QuantumErrorCorrection class."""

    @pytest.fixture
    def qbit(self) -> QuantumBit:
        """Fixture providing a quantum bit."""
        return QuantumBit('0')

    @pytest.fixture
    def qec(self, qbit: QuantumBit) -> QuantumErrorCorrection:
        """Fixture providing quantum error correction instance."""
        return QuantumErrorCorrection(qbit)

    def test_initialization(self, qec: QuantumErrorCorrection) -> None:
        """Test QEC initialization."""
        assert qec.qubit.state == QuantumState.ZERO
        assert not qec.qubit.is_encoded
        assert qec.threshold == 0.5
        assert isinstance(qec.metrics, QuantumMetrics)

    def test_initialization_with_invalid_threshold(self, qbit: QuantumBit) -> None:
        """Test that invalid threshold raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            QuantumErrorCorrection(qbit, threshold=1.5)
        assert "Threshold must be in" in str(exc_info.value)

    def test_initialization_with_invalid_threshold_negative(self, qbit: QuantumBit) -> None:
        """Test that negative threshold raises ValueError."""
        with pytest.raises(ValueError):
            QuantumErrorCorrection(qbit, threshold=-0.1)

    def test_encode_success(self, qec: QuantumErrorCorrection) -> None:
        """Test successful encoding."""
        encoded_state = qec.encode()
        assert qec.qubit.is_encoded
        assert len(qec.physical_qubits) == 4
        assert qec.metrics.encoding_count == 1
        assert isinstance(encoded_state, str)

    def test_encode_already_encoded_raises_error(self, qec: QuantumErrorCorrection) -> None:
        """Test that encoding an already-encoded qubit raises error."""
        qec.encode()
        with pytest.raises(EncodingError) as exc_info:
            qec.encode()
        assert "already encoded" in str(exc_info.value)

    def test_encode_with_different_states(self) -> None:
        """Test encoding works with all valid quantum states."""
        for state_val in ['0', '1', '+', '-']:
            qbit = QuantumBit(state_val)
            qec = QuantumErrorCorrection(qbit)
            encoded = qec.encode()
            assert qec.qubit.is_encoded
            assert encoded is not None

    def test_syndrome_measurement_without_encoding_raises_error(
        self, qec: QuantumErrorCorrection
    ) -> None:
        """Test that syndrome measurement on non-encoded qubit raises error."""
        with pytest.raises(CorrectionError) as exc_info:
            qec.measure_syndrome()
        assert "must be encoded" in str(exc_info.value)

    def test_syndrome_measurement_success(self, qec: QuantumErrorCorrection) -> None:
        """Test successful syndrome measurement."""
        qec.encode()
        syndrome = qec.measure_syndrome()
        assert isinstance(syndrome, SyndromeResult)
        assert syndrome.parity_x in [0, 1]
        assert syndrome.parity_z in [0, 1]
        assert isinstance(syndrome.is_valid, bool)

    def test_correction_without_encoding_raises_error(
        self, qec: QuantumErrorCorrection
    ) -> None:
        """Test that correction on non-encoded qubit raises error."""
        with pytest.raises(CorrectionError) as exc_info:
            qec.correct()
        assert "must be encoded" in str(exc_info.value)

    def test_correction_with_syndrome(self, qec: QuantumErrorCorrection) -> None:
        """Test correction with provided syndrome."""
        qec.encode()
        syndrome = SyndromeResult(parity_x=1, parity_z=0, is_valid=False, error_type="bit_flip")
        corrected = qec.correct(syndrome)
        assert qec.metrics.correction_count == 1
        assert qec.metrics.errors_corrected == 1
        assert isinstance(corrected, str)

    def test_correction_without_error(self, qec: QuantumErrorCorrection) -> None:
        """Test correction when no error is detected."""
        qec.encode()
        syndrome = SyndromeResult(parity_x=0, parity_z=0, is_valid=True, error_type=None)
        corrected = qec.correct(syndrome)
        assert qec.metrics.correction_count == 1
        assert qec.metrics.errors_corrected == 0

    def test_decode_without_encoding_raises_error(
        self, qec: QuantumErrorCorrection
    ) -> None:
        """Test that decoding non-encoded qubit raises error."""
        with pytest.raises(DecodingError) as exc_info:
            qec.decode()
        assert "must be encoded" in str(exc_info.value)

    def test_decode_success(self, qec: QuantumErrorCorrection) -> None:
        """Test successful decoding."""
        qec.encode()
        decoded = qec.decode()
        assert not qec.qubit.is_encoded
        assert qec.metrics.decoding_count == 1
        assert isinstance(decoded, str)

    def test_full_encode_correct_decode_cycle(self, qec: QuantumErrorCorrection) -> None:
        """Test complete encode-correct-decode cycle."""
        # Encode
        qec.encode()
        assert qec.qubit.is_encoded

        # Measure syndrome
        syndrome = qec.measure_syndrome()
        assert isinstance(syndrome, SyndromeResult)

        # Correct
        qec.correct(syndrome)
        assert qec.metrics.correction_count == 1

        # Decode
        decoded = qec.decode()
        assert not qec.qubit.is_encoded
        assert qec.metrics.decoding_count == 1

    def test_get_metrics(self, qec: QuantumErrorCorrection) -> None:
        """Test retrieving metrics."""
        metrics = qec.get_metrics()
        assert isinstance(metrics, QuantumMetrics)
        assert metrics.encoding_count == 0
        assert metrics.decoding_count == 0
        assert metrics.correction_count == 0

    def test_get_error_history(self, qec: QuantumErrorCorrection) -> None:
        """Test retrieving error history."""
        history = qec.get_error_history()
        assert history == []

        qec.qubit.record_error("test_error")
        history = qec.get_error_history()
        assert "test_error" in history

    def test_error_model_integration(self) -> None:
        """Test integration with error model."""
        qbit = QuantumBit('0')
        error_model = DepolarizingError()
        qec = QuantumErrorCorrection(qbit, error_model=error_model)
        assert qec.error_model == error_model

    def test_metrics_accumulation(self, qec: QuantumErrorCorrection) -> None:
        """Test that metrics accumulate correctly."""
        # Multiple encode-decode cycles
        for _ in range(3):
            qec.encode()
            qec.decode()

        metrics = qec.get_metrics()
        assert metrics.encoding_count == 3
        assert metrics.decoding_count == 3


class TestSyndromeResult:
    """Test cases for SyndromeResult dataclass."""

    def test_syndrome_creation(self) -> None:
        """Test syndrome result creation."""
        syndrome = SyndromeResult(parity_x=0, parity_z=1, is_valid=False, error_type="phase_flip")
        assert syndrome.parity_x == 0
        assert syndrome.parity_z == 1
        assert syndrome.is_valid is False
        assert syndrome.error_type == "phase_flip"

    def test_syndrome_default_values(self) -> None:
        """Test syndrome result with default values."""
        syndrome = SyndromeResult(parity_x=0, parity_z=0)
        assert syndrome.is_valid is True
        assert syndrome.error_type is None


class TestQuantumMetrics:
    """Test cases for QuantumMetrics dataclass."""

    def test_metrics_initialization(self) -> None:
        """Test metrics initialization with defaults."""
        metrics = QuantumMetrics()
        assert metrics.encoding_count == 0
        assert metrics.decoding_count == 0
        assert metrics.correction_count == 0
        assert metrics.errors_detected == 0
        assert metrics.errors_corrected == 0
        assert metrics.syndrome_failures == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
