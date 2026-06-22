# Quantum Error Correction Codex: Harmonic Geometry Framework

A fault-tolerant quantum error correction implementation built on **Platonic solid architecture** and **harmonic resonance principles** (3-6-9 fundamental patterns).

## Overview

This framework organizes quantum error correction through 5 layers of geometric and harmonic structure:

1. **Tetrahedron (4)** — Foundation state: 4-qubit base locked in quantum substrate
2. **Cube (6)** — Stabilization: 6 stabilizer generators encoding present state
3. **Octahedron (3-6)** — Syndrome Detection Bridge: harmonic measurement and syndrome mapping
4. **Dodecahedron (9)** — Error Transformation: 9-parameter correction space
5. **Icosahedron (9+vortex)** — Recursive Vortex Flow: recursive spiraling correction

Each Platonic solid maps to:
- **Frequency harmonics**: 3-6-9 resonance ratios
- **Rotation angles**: 30° (3), 60° (6), 90° (9)
- **Quantum operations**: encoding, measurement, and correction
- **Error mapping**: syndrome patterns to harmonic correction parameters

## Architecture

```
Tetrahedron (Foundation)
    ↓
Cube (Stabilization)
    ↓
Octahedron (Syndrome Bridge)
    ↓
Dodecahedron (Error Transformation)
    ↓
Icosahedron (Recursive Correction)
```

## Installation

```bash
git clone https://github.com/mrwinsalot88-creator/quantum-ecc-fault-tolerant-btbc
cd quantum-ecc-fault-tolerant-btbc
pip install -r requirements.txt
```

## Usage

### Basic Example

```python
from quantum_ecc import QuantumErrorCorrectionCodex

# Create the complete framework
codex = QuantumErrorCorrectionCodex()

# Run full encode → measure → correct cycle
result = codex.run_full_correction_cycle(logical_state=0)

print(f"Logical State: {result['logical_state']}")
print(f"Syndrome: {result['syndrome']:06b}")
print(f"Circuit Depth: {result['circuit_depth']}")
print(f"Stabilizers: {result['stabilizers']}")
```

### Step-by-Step Encoding

```python
from quantum_ecc import QuantumErrorCorrectionCodex

codex = QuantumErrorCorrectionCodex()

# Step 1: Encode logical qubit through Tetrahedron + Cube
qc, qr = codex.encode_logical_qubit(logical_state=1)

# Step 2: Measure syndrome through Octahedron
qc_measure, cr = codex.measure_syndrome(qc, qr)

# Step 3: Apply correction through Dodecahedron + Icosahedron
qc_corrected = codex.correct_error(qc, qr, syndrome_result=5)
```

## Classes

### `HarmonicGeometry`
Maps frequency, angles, and resonance patterns to quantum parameters.

- `FUNDAMENTAL_RATIOS`: 3-6-9 resonance ratios
- `PLATONIC_DIMENSIONS`: Vertex/edge counts for each solid
- `FREQUENCY_ANGLES`: Frequency-to-rotation-angle mappings
- `harmonic_gate_angle(frequency, phase)`: Calculate rotation angle from harmonic frequency

### `Tetrahedron`
Foundation layer: creates 4-qubit base and encodes logical state.

- `create_circuit()`: Create base 4-qubit quantum circuit
- `encode_logical_state(qc, qr, logical_state)`: Encode 0 or 1

### `Cube`
Stabilization layer: 6 stabilizer generators using harmonic angles.

- `build_stabilizer_circuit(qr)`: Build 6-stabilizer encoding
- `stabilizer_generators()`: Return stabilizer definitions (XXII, IXXI, etc.)

### `Octahedron`
Syndrome detection bridge: measure syndromes using 3-6 harmonic patterns.

- `build_syndrome_circuit(qr, stabilizers)`: Build syndrome measurement
- `decode_syndrome(syndrome)`: Map syndrome bits to error types and frequencies

### `Dodecahedron`
Error transformation: 9-parameter correction space.

- `build_correction_circuit(qr, syndrome)`: Build correction operations

### `Icosahedron`
Recursive vortex flow: spiraling corrections through rotation matrices.

- `build_vortex_circuit(qr, syndrome, iterations)`: Build recursive corrections

### `QuantumErrorCorrectionCodex`
Complete framework orchestrating all 5 layers.

- `encode_logical_qubit(logical_state)`: Encode through Tetrahedron + Cube
- `measure_syndrome(qc, qr)`: Measure through Octahedron
- `correct_error(qc, qr, syndrome_result)`: Apply correction through Dodeca + Icosa
- `run_full_correction_cycle(logical_state)`: Full encode → measure → correct

## Testing

Run the comprehensive test suite:

```bash
python -m pytest test_quantum_ecc.py -v
```

Or with unittest:

```bash
python test_quantum_ecc.py
```

Tests cover:
- Harmonic geometry mappings (3-6-9 frequencies)
- Each Platonic solid layer
- Full correction cycles
- Syndrome decoding
- Circuit construction

## Design Principles

### Harmonic Resonance
The framework uses 3-6-9 as fundamental organizing frequencies:
- **3**: Detection and measurement (Octahedron)
- **6**: Stabilization and present state (Cube)
- **9**: Transformation and recursive flow (Dodecahedron + Icosahedron)

### Platonic Geometry
Each solid represents a distinct quantum operation phase:
- **Tetrahedron (4)**: Foundation — locked substrate
- **Cube (6)**: Present — stabilization now
- **Octahedron (3-6)**: Bridge — measurement and detection
- **Dodecahedron (9)**: Future — transformation parameters
- **Icosahedron (9+vortex)**: Flow — recursive refinement

### Unified Mappings
Frequency → Angle → Quantum Gate
- 3 Hz → 30° (π/6) → Rotation gates
- 6 Hz → 60° (π/3) → Stabilizer operations
- 9 Hz → 90° (π/2) → Complete transformations

## Mathematical Foundation

### Stabilizer Generators
The 6 stabilizer generators from the Cube layer:
```
S1: XXII  (X basis on qubits 0,1)
S2: IXXI  (X basis on qubits 1,2)
S3: IIXX  (X basis on qubits 2,3)
S4: ZZII  (Z basis on qubits 0,1)
S5: IZZI  (Z basis on qubits 1,2)
S6: IIZZ  (Z basis on qubits 2,3)
```

### Syndrome Decoding
Syndrome bits map to error frequencies:
- Bits 0-2: 3-frequency errors
- Bits 3-5: 6-frequency errors

### Vortex Correction
Icosahedron layer applies 9-parameter corrections in spiral pattern:
```
Iteration 0: RX gates
Iteration 1: RY gates
Iteration 2: RZ gates
(repeats with phase shifts)
```

## References

- Qiskit Documentation: https://qiskit.org/
- Quantum Error Correction Theory: https://arxiv.org/abs/quant-ph/0110143
- Platonic Solids in Physics: https://en.wikipedia.org/wiki/Platonic_solid

## Contributing

Contributions welcome. Areas for expansion:
- Additional error models (depolarizing, amplitude damping)
- More sophisticated syndrome decoding
- Optimization of gate sequences
- Integration with real quantum hardware
- Extended harmonic framework analysis

## License

MIT License - See LICENSE file for details

## Author
Dan Brown

Built with harmonic geometry and quantum error correction principles.
