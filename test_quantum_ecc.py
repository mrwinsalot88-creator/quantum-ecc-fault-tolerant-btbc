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
import unittest
from quantum_ecc import (
    TrinaryErrorCorrectionCodex,
    TrinaryPole,
    ErrorType,
    HarmonicGeometry,
    TrinaryState,
    Tetrahedron,
    Cube,
    Octahedron,
    Dodecahedron,
    Icosahedron
)
import numpy as np


class TestHarmonicGeometry(unittest.TestCase):
    """Test harmonic geometry and 3-6-9 pole mappings"""
    
    def test_trinary_pole_angles(self):
        """Test that trinary poles map to 3-6-9 angles"""
        angle_neg = HarmonicGeometry.get_pole_angle(TrinaryPole.NEGATIVE)
        angle_neut = HarmonicGeometry.get_pole_angle(TrinaryPole.NEUTRAL)
        angle_pos = HarmonicGeometry.get_pole_angle(TrinaryPole.POSITIVE)
        
        # -1 pole: 30° (π/6, 3-frequency)
        self.assertAlmostEqual(angle_neg, np.pi / 6)
        # 0 pole: 60° (π/3, 6-frequency)
        self.assertAlmostEqual(angle_neut, np.pi / 3)
        # +1 pole: 90° (π/2, 9-frequency)
        self.assertAlmostEqual(angle_pos, np.pi / 2)
    
    def test_pole_from_angle_at_poles(self):
        """Test angle-to-pole detection when state is on a pole"""
        # Test at -1 pole
        pole = HarmonicGeometry.pole_from_angle(np.pi / 6)
        self.assertEqual(pole, TrinaryPole.NEGATIVE)
        
        # Test at 0 pole
        pole = HarmonicGeometry.pole_from_angle(np.pi / 3)
        self.assertEqual(pole, TrinaryPole.NEUTRAL)
        
        # Test at +1 pole
        pole = HarmonicGeometry.pole_from_angle(np.pi / 2)
        self.assertEqual(pole, TrinaryPole.POSITIVE)
    
    def test_pole_from_angle_off_pole_detection(self):
        """Test angle-to-pole detection when state is off a pole"""
        # Angle clearly off all poles
        pole = HarmonicGeometry.pole_from_angle(0.0)
        self.assertIsNone(pole)  # Indicates error state
    
    def test_frequency_shift_detection(self):
        """Test beat frequency calculation"""
        # At -1 pole, no beat frequency
        beat = HarmonicGeometry.detect_frequency_shift(np.pi / 6, TrinaryPole.NEGATIVE)
        self.assertAlmostEqual(beat, 0.0)
        
        # Shifted 0.1 radians from -1 pole
        beat = HarmonicGeometry.detect_frequency_shift(np.pi / 6 + 0.1, TrinaryPole.NEGATIVE)
        self.assertAlmostEqual(beat, 0.1)


class TestTrinaryState(unittest.TestCase):
    """Test individual trinary state behavior"""
    
    def test_state_creation_with_pole(self):
        """Test creating state at a specific pole"""
        state = TrinaryState(TrinaryPole.POSITIVE)
        self.assertEqual(state.pole, TrinaryPole.POSITIVE)
        self.assertAlmostEqual(state.angle, np.pi / 2)
    
    def test_state_error_detection_clean(self):
        """Test that clean state has no error"""
        state = TrinaryState(TrinaryPole.NEGATIVE)
        has_error, error_type = state.detect_error()
        self.assertFalse(has_error)
        self.assertIsNone(error_type)
    
    def test_state_error_detection_frequency_shift(self):
        """Test detection of frequency shift error"""
        state = TrinaryState(TrinaryPole.NEUTRAL, angle=np.pi / 3 + 0.2)
        has_error, error_type = state.detect_error()
        self.assertTrue(has_error)
        self.assertEqual(error_type, ErrorType.FREQUENCY_SHIFT)
    
    def test_state_error_detection_polarity_inversion(self):
        """Test detection of polarity inversion error"""
        # State initialized as -1 but angle shifted to +1 pole
        state = TrinaryState(TrinaryPole.NEGATIVE, angle=np.pi / 2 + 0.3)
        has_error, error_type = state.detect_error()
        self.assertTrue(has_error)
        self.assertEqual(error_type, ErrorType.POLARITY_INVERSION)
    
    def test_state_error_detection_center_drift(self):
        """Test detection of center drift error"""
        # Small deviation toward neutral pole
        state = TrinaryState(TrinaryPole.NEGATIVE, angle=np.pi / 6 + 0.05)
        has_error, error_type = state.detect_error()
        self.assertTrue(has_error)
        self.assertEqual(error_type, ErrorType.CENTER_DRIFT)
    
    def test_state_restoration_to_pole(self):
        """Test that restoration pulls state back to pole"""
        # State with frequency shift error
        state = TrinaryState(TrinaryPole.POSITIVE, angle=np.pi / 2 + 0.2)
        has_error, error_type = state.detect_error()
        self.assertTrue(has_error)
        
        # Restore to +1 pole
        state.restore(TrinaryPole.POSITIVE)
        
        # Should be back at +1 pole
        self.assertAlmostEqual(state.angle, np.pi / 2, places=5)
        self.assertEqual(state.pole, TrinaryPole.POSITIVE)
        self.assertIsNone(state.error_type)


class TestTetrahedron(unittest.TestCase):
    """Test Tetrahedron foundation layer"""
    
    def setUp(self):
        self.tet = Tetrahedron()
    
    def test_tetrahedron_has_4_faces(self):
        """Test that Tetrahedron has 4 faces"""
        self.assertEqual(len(self.tet.states), 4)
        self.assertEqual(self.tet.n_faces, 4)
    
    def test_tetrahedron_initialization_negative(self):
        """Test initialization to -1 logical value"""
        self.tet.initialize_logical_state(-1)
        
        # First 3 faces should be -1 pole
        for i in range(3):
            self.assertEqual(self.tet.states[i].pole, TrinaryPole.NEGATIVE)
        
        # 4th face (center) should be neutral
        self.assertEqual(self.tet.states[3].pole, TrinaryPole.NEUTRAL)
    
    def test_tetrahedron_initialization_neutral(self):
        """Test initialization to 0 logical value"""
        self.tet.initialize_logical_state(0)
        
        # First 3 faces should be neutral
        for i in range(3):
            self.assertEqual(self.tet.states[i].pole, TrinaryPole.NEUTRAL)
    
    def test_tetrahedron_initialization_positive(self):
        """Test initialization to +1 logical value"""
        self.tet.initialize_logical_state(1)
        
        # First 3 faces should be +1 pole
        for i in range(3):
            self.assertEqual(self.tet.states[i].pole, TrinaryPole.POSITIVE)
    
    def test_tetrahedron_center_lock(self):
        """Test that center face locks at neutral pole"""
        self.tet.initialize_logical_state(1)
        
        # Artificially drift the center
        self.tet.states[3].angle = 0.5
        
        # Lock it
        self.tet.lock_center()
        
        # Should snap back to neutral
        self.assertAlmostEqual(self.tet.states[3].angle, np.pi / 3)


class TestCube(unittest.TestCase):
    """Test Cube stabilization layer"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
    
    def test_cube_has_6_error_states(self):
        """Test that Cube has 6 error states"""
        self.assertEqual(self.cube.n_faces, 6)
        self.assertEqual(len(self.cube.error_states), 6)
    
    def test_cube_stabilizer_generators(self):
        """Test that stabilizer generators are correctly defined"""
        stabs = self.cube.get_stabilizer_generators()
        self.assertEqual(len(stabs), 6)
        
        # Should have 3-frequency and 6-frequency generators
        self.assertIn("3-FREQ-NEG", stabs)
        self.assertIn("3-FREQ-NEUT", stabs)
        self.assertIn("3-FREQ-POS", stabs)
        self.assertIn("6-FREQ-NEG", stabs)
        self.assertIn("6-FREQ-NEUT", stabs)
        self.assertIn("6-FREQ-POS", stabs)
    
    def test_cube_stabilization_reinforcement(self):
        """Test that stabilization reinforces states toward their poles"""
        self.tet.initialize_logical_state(1)
        
        # Drift the states
        for state in self.tet.states[:3]:
            state.angle += 0.1
        
        # Stabilize
        stabilized = self.cube.stabilize()
        
        # Should be closer to +1 pole than before
        for i in range(3):
            self.assertLess(
                abs(stabilized[i].angle - np.pi / 2),
                abs(self.tet.states[i].angle - np.pi / 2)
            )


class TestOctahedron(unittest.TestCase):
    """Test Octahedron syndrome detection bridge"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
    
    def test_octahedron_has_8_vertices(self):
        """Test that Octahedron has 8 vertices (3 poles + 6 directions)"""
        self.assertEqual(self.octa.n_vertices, 8)
        self.assertEqual(len(self.octa.poles), 3)
        self.assertEqual(len(self.octa.harmonic_directions), 6)
    
    def test_syndrome_measurement_no_error(self):
        """Test syndrome measurement when no errors present"""
        self.tet.initialize_logical_state(1)
        stabilized = self.cube.stabilize()
        syndromes = self.octa.measure_syndromes(stabilized)
        
        # All states should be error-free
        for state_id, syndrome in syndromes.items():
            self.assertFalse(syndrome['has_error'])
            self.assertEqual(syndrome['error_type'], 'NONE')
    
    def test_syndrome_measurement_with_error(self):
        """Test syndrome measurement detects injected error"""
        self.tet.initialize_logical_state(1)
        
        # Inject frequency shift error
        self.tet.states[0].angle += 0.3
        
        syndromes = self.octa.measure_syndromes(self.tet.states)
        
        # State 0 should show error
        self.assertTrue(syndromes['state_0']['has_error'])
        self.assertEqual(syndromes['state_0']['error_type'], 'FREQUENCY_SHIFT')
    
    def test_syndrome_decoding(self):
        """Test that syndromes decode to correction instructions"""
        self.tet.initialize_logical_state(1)
        self.tet.states[0].angle += 0.25  # Frequency shift
        
        syndromes = self.octa.measure_syndromes(self.tet.states)
        corrections = self.octa.decode_syndrome(syndromes)
        
        # Should have correction for state_0
        self.assertIn('state_0', corrections)
        self.assertEqual(corrections['state_0']['error_type'], 'FREQUENCY_SHIFT')
        self.assertEqual(corrections['state_0']['target_pole'], 'POSITIVE')


class TestDodecahedron(unittest.TestCase):
    """Test Dodecahedron error transformation"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
        self.dodeca = Dodecahedron(self.octa)
    
    def test_dodecahedron_has_9_parameters(self):
        """Test that Dodecahedron has 9 restoration parameters"""
        self.assertEqual(self.dodeca.n_axes, 9)
        self.assertEqual(len(self.dodeca.restoration_params), 9)
    
    def test_restoration_matrix_structure(self):
        """Test that restoration matrix has correct structure"""
        matrix = self.dodeca.get_restoration_matrix()
        
        # Should have 9 parameters: 3 poles × 3 error types
        self.assertEqual(len(matrix), 9)
        
        # Each combination should exist
        self.assertIn('NEG_freq_shift', matrix)
        self.assertIn('NEUT_polarity', matrix)
        self.assertIn('POS_center_drift', matrix)
    
    def test_restoration_application(self):
        """Test that restoration corrects states"""
        self.tet.initialize_logical_state(1)
        self.tet.states[0].angle = np.pi / 2 + 0.2  # Frequency shift error
        
        syndromes = self.octa.measure_syndromes(self.tet.states)
        corrections = self.octa.decode_syndrome(syndromes)
        
        restored = self.dodeca.apply_restoration(self.tet.states, corrections)
        
        # State 0 should be corrected
        self.assertAlmostEqual(restored[0].angle, np.pi / 2, places=5)


class TestIcosahedron(unittest.TestCase):
    """Test Icosahedron recursive vortex flow"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
        self.dodeca = Dodecahedron(self.octa)
        self.icosa = Icosahedron(self.dodeca)
    
    def test_icosahedron_has_vortex_iterations(self):
        """Test that Icosahedron has vortex iteration count"""
        self.assertEqual(self.icosa.vortex_iterations, 3)
        self.assertEqual(self.icosa.n_faces, 20)
    
    def test_vortex_convergence(self):
        """Test that vortex spiral converges to nearest pole"""
        # Create a state off-pole
        state = TrinaryState(TrinaryPole.POSITIVE, angle=np.pi / 2 + 0.3)
        states = [state]
        
        # Apply vortex
        corrected = self.icosa.apply_vortex_correction(states, iterations=3)
        
        # Should converge toward +1 pole
        self.assertLess(corrected[0].angle, state.angle)
        self.assertLess(abs(corrected[0].angle - np.pi / 2), 0.2)


class TestTrinaryErrorCorrectionCodex(unittest.TestCase):
    """Test complete trinary error correction framework"""
    
    def setUp(self):
        self.codex = TrinaryErrorCorrectionCodex()
    
    def test_codex_initialization(self):
        """Test that codex initializes all 5 layers"""
        self.assertIsNotNone(self.codex.tet)
        self.assertIsNotNone(self.codex.cube)
        self.assertIsNotNone(self.codex.octa)
        self.assertIsNotNone(self.codex.dodeca)
        self.assertIsNotNone(self.codex.icosa)
    
    def test_full_cycle_no_error(self):
        """Test full correction cycle with no injected error"""
        result = self.codex.run_full_cycle(logical_value=1)
        
        self.assertEqual(result['logical_value'], 1)
        self.assertEqual(result['error_injected'], 'NONE')
        self.assertIn('measurement', result)
        self.assertIn('correction', result)
    
    def test_full_cycle_frequency_shift(self):
        """Test full correction cycle with frequency shift error"""
        result = self.codex.run_full_cycle(
            logical_value=1,
            error_state_index=0,
            error_type=ErrorType.FREQUENCY_SHIFT
        )
        
        self.assertEqual(result['logical_value'], 1)
        self.assertEqual(result['error_injected'], 'FREQUENCY_SHIFT')
        
        # Should detect the error
        syndromes = result['measurement']['syndromes']
        self.assertTrue(syndromes['state_0']['has_error'])
        self.assertEqual(syndromes['state_0']['error_type'], 'FREQUENCY_SHIFT')
    
    def test_full_cycle_polarity_inversion(self):
        """Test full correction cycle with polarity inversion error"""
        result = self.codex.run_full_cycle(
            logical_value=-1,
            error_state_index=1,
            error_type=ErrorType.POLARITY_INVERSION
        )
        
        self.assertEqual(result['logical_value'], -1)
        self.assertEqual(result['error_injected'], 'POLARITY_INVERSION')
        
        # Should detect polarity inversion
        syndromes = result['measurement']['syndromes']
        self.assertTrue(syndromes['state_1']['has_error'])
    
    def test_full_cycle_center_drift(self):
        """Test full correction cycle with center drift error"""
        result = self.codex.run_full_cycle(
            logical_value=0,
            error_state_index=0,
            error_type=ErrorType.CENTER_DRIFT
        )
        
        self.assertEqual(result['logical_value'], 0)
        self.assertEqual(result['error_injected'], 'CENTER_DRIFT')
        self.assertTrue(result['measurement']['syndromes']['state_0']['has_error'])
    
    def test_correction_restores_state(self):
        """Test that correction process restores corrupted states"""
        # Inject error
        result = self.codex.run_full_cycle(
            logical_value=1,
            error_state_index=0,
            error_type=ErrorType.FREQUENCY_SHIFT
        )
        
        # Check final state
        final_states = result['correction']['final_states']
        
        # Face 0 should be restored to +1 pole (90°)
        # Extract from string representation
        face_0_str = final_states['face_0']
        self.assertIn('POSITIVE', face_0_str)  # Should be back at +1 pole


if __name__ == '__main__':
    unittest.main(verbosity=2)
