import unittest
from quantum_ecc import (
    QuantumErrorCorrectionCodex,
    HarmonicGeometry,
    Tetrahedron,
    Cube,
    Octahedron,
    Dodecahedron,
    Icosahedron
)
import numpy as np


class TestHarmonicGeometry(unittest.TestCase):
    """Test harmonic geometry mappings"""
    
    def test_frequency_angles(self):
        """Test 3-6-9 frequency to angle mappings"""
        angle_3 = HarmonicGeometry.harmonic_gate_angle(3)
        angle_6 = HarmonicGeometry.harmonic_gate_angle(6)
        angle_9 = HarmonicGeometry.harmonic_gate_angle(9)
        
        self.assertAlmostEqual(angle_3, np.pi / 6)
        self.assertAlmostEqual(angle_6, np.pi / 3)
        self.assertAlmostEqual(angle_9, np.pi / 2)
    
    def test_platonic_dimensions(self):
        """Test Platonic solid dimension mappings"""
        dims = HarmonicGeometry.PLATONIC_DIMENSIONS
        self.assertEqual(dims['tetrahedron'], 4)
        self.assertEqual(dims['cube'], 6)
        self.assertEqual(dims['octahedron'], 12)
        self.assertEqual(dims['dodecahedron'], 9)
        self.assertEqual(dims['icosahedron'], 20)


class TestTetrahedron(unittest.TestCase):
    """Test Tetrahedron foundation layer"""
    
    def setUp(self):
        self.tet = Tetrahedron()
    
    def test_create_circuit(self):
        """Test creating base 4-qubit circuit"""
        qc, qr = self.tet.create_circuit()
        self.assertEqual(qc.num_qubits, 4)
        self.assertEqual(len(qr), 4)
    
    def test_encode_logical_0(self):
        """Test encoding logical 0"""
        qc, qr = self.tet.create_circuit()
        qc = self.tet.encode_logical_state(qc, qr, 0)
        # Logical 0 should not apply any gates
        self.assertEqual(qc.size(), 0)
    
    def test_encode_logical_1(self):
        """Test encoding logical 1"""
        qc, qr = self.tet.create_circuit()
        qc = self.tet.encode_logical_state(qc, qr, 1)
        # Logical 1 should apply X gate to first qubit
        self.assertGreater(qc.size(), 0)


class TestCube(unittest.TestCase):
    """Test Cube stabilization layer"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
    
    def test_stabilizer_generators(self):
        """Test 6 stabilizer generator definitions"""
        stabs = self.cube.stabilizer_generators()
        self.assertEqual(len(stabs), 6)
        self.assertIn("XXII", stabs)
        self.assertIn("ZZII", stabs)
    
    def test_stabilizer_circuit(self):
        """Test building stabilizer circuit"""
        qc, qr = self.tet.create_circuit()
        stab_qc = self.cube.build_stabilizer_circuit(qr)
        self.assertEqual(stab_qc.num_qubits, 4)


class TestOctahedron(unittest.TestCase):
    """Test Octahedron syndrome detection bridge"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
    
    def test_decode_syndrome(self):
        """Test syndrome decoding to error mapping"""
        # Test syndrome 0b000011 (bits 0,1 set)
        syndrome = 0b000011
        error_map = self.octa.decode_syndrome(syndrome)
        
        # Should map to errors at qubits 0 and 1
        self.assertIn('qubit_0', error_map)
        self.assertIn('qubit_1', error_map)
        
        # Check harmonic frequency assignment
        self.assertEqual(error_map['qubit_0']['frequency'], 3)
        self.assertEqual(error_map['qubit_1']['frequency'], 3)


class TestDodecahedron(unittest.TestCase):
    """Test Dodecahedron error transformation"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
        self.dodeca = Dodecahedron(self.octa)
    
    def test_correction_parameters(self):
        """Test 9-parameter correction space"""
        self.assertEqual(self.dodeca.n_correction_params, 9)
    
    def test_correction_circuit(self):
        """Test building correction circuit"""
        qc, qr = self.tet.create_circuit()
        
        # Create a simple error map
        error_map = {'qubit_0': {'type': 'flip', 'frequency': 3}}
        
        corr_qc = self.dodeca.build_correction_circuit(qr, error_map)
        self.assertEqual(corr_qc.num_qubits, 4)


class TestIcosahedron(unittest.TestCase):
    """Test Icosahedron recursive vortex flow"""
    
    def setUp(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
        self.dodeca = Dodecahedron(self.octa)
        self.icosa = Icosahedron(self.dodeca)
    
    def test_vortex_iterations(self):
        """Test vortex iteration count"""
        self.assertEqual(self.icosa.vortex_iterations, 3)
    
    def test_vortex_circuit(self):
        """Test building vortex flow circuit"""
        qc, qr = self.tet.create_circuit()
        error_map = {'qubit_0': {'type': 'flip', 'frequency': 3}}
        
        vortex_qc = self.icosa.build_vortex_circuit(qr, error_map, iterations=2)
        self.assertEqual(vortex_qc.num_qubits, 4)


class TestQuantumErrorCorrectionCodex(unittest.TestCase):
    """Test complete QEC framework"""
    
    def setUp(self):
        self.codex = QuantumErrorCorrectionCodex()
    
    def test_encode_logical_qubit(self):
        """Test encoding logical qubit"""
        qc, qr = self.codex.encode_logical_qubit(logical_state=0)
        self.assertEqual(qc.num_qubits, 4)
    
    def test_full_correction_cycle_logical_0(self):
        """Test complete correction cycle with logical 0"""
        result = self.codex.run_full_correction_cycle(logical_state=0)
        
        self.assertEqual(result['logical_state'], 0)
        self.assertIn('syndrome', result)
        self.assertIn('circuit_depth', result)
        self.assertEqual(result['n_qubits'], 4)
        self.assertEqual(len(result['stabilizers']), 6)
    
    def test_full_correction_cycle_logical_1(self):
        """Test complete correction cycle with logical 1"""
        result = self.codex.run_full_correction_cycle(logical_state=1)
        
        self.assertEqual(result['logical_state'], 1)
        self.assertIn('syndrome', result)
        self.assertGreater(result['circuit_depth'], 0)
    
    def test_codex_architecture(self):
        """Test that all layers are present"""
        self.assertIsNotNone(self.codex.tet)
        self.assertIsNotNone(self.codex.cube)
        self.assertIsNotNone(self.codex.octa)
        self.assertIsNotNone(self.codex.dodeca)
        self.assertIsNotNone(self.codex.icosa)


if __name__ == '__main__':
    unittest.main()
