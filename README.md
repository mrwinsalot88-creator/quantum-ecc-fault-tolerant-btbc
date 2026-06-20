# Quantum Error Correction (QEC) - Production Grade Implementation

## Overview

This repository contains a production-grade implementation of fault-tolerant quantum error correction using a [[4,1,2]] logical qubit encoding with active error correction capabilities.

## Features

### Code Quality
- ✅ **Type Hints**: Full typing support for IDE autocomplete and type checking
- ✅ **Error Handling**: Custom exception hierarchy for clear error semantics
- ✅ **Input Validation**: Comprehensive validation of quantum states and parameters
- ✅ **Comprehensive Logging**: Observable state for debugging and monitoring
- ✅ **Observable Metrics**: Detailed metrics for operational insights

### Quantum Capabilities
- 🔬 **[[4,1,2]] Encoding**: 1 logical qubit → 4 physical qubits
- 🔍 **Syndrome Measurement**: Detect single-qubit errors
- ⚙️ **Active Correction**: Automated error recovery
- 📊 **Error History**: Track detected errors over time
- 🛠️ **Configurable Error Models**: Pluggable error simulation

## Architecture

### Module Structure

```
quantum_ecc/
├── quantum_ecc.py          # Core QEC implementation
├── config.py               # Configuration management
├── test_quantum_ecc.py     # Comprehensive test suite
└── requirements.txt        # Dependencies
```

### Key Classes

#### `QuantumBit`
Represents a single logical quantum bit with state tracking and error history.

```python
from quantum_ecc import QuantumBit

# Valid states: '0', '1', '+', '-'
qbit = QuantumBit('0')
print(qbit.state)      # QuantumState.ZERO
print(qbit.is_encoded) # False
```

#### `QuantumErrorCorrection`
Provides fault-tolerant quantum error correction with encode/correct/decode cycle.

```python
from quantum_ecc import QuantumErrorCorrection, QuantumBit

qbit = QuantumBit('0')
qec = QuantumErrorCorrection(qubit=qbit, threshold=0.5)

# Encode logical qubit into 4 physical qubits
encoded = qec.encode()

# Measure syndrome to detect errors
syndrome = qec.measure_syndrome()

# Apply error correction based on syndrome
corrected = qec.correct(syndrome)

# Decode back to logical qubit
decoded = qec.decode()

# Check metrics
metrics = qec.get_metrics()
print(f"Errors corrected: {metrics.errors_corrected}")
```

#### `SyndromeResult`
Results from error syndrome measurement with error type inference.

```python
from quantum_ecc import SyndromeResult

syndrome = SyndromeResult(
    parity_x=1, 
    parity_z=0, 
    is_valid=False, 
    error_type="bit_flip"
)
```

#### `QuantumMetrics`
Observable metrics for tracking QEC operation statistics.

```python
from quantum_ecc import QuantumMetrics

metrics = QuantumMetrics()
print(f"Encoding operations: {metrics.encoding_count}")
print(f"Errors detected: {metrics.errors_detected}")
print(f"Errors corrected: {metrics.errors_corrected}")
```

## Error Handling

The module provides a custom exception hierarchy for clear error semantics:

```python
from quantum_ecc import (
    QuantumECCException,        # Base exception
    InvalidQuantumStateError,   # Invalid state
    EncodingError,              # Encoding failure
    CorrectionError,            # Correction failure
    DecodingError,              # Decoding failure
)

try:
    qbit = QuantumBit('invalid')
except InvalidQuantumStateError as e:
    print(f"Invalid state: {e}")
```

## Configuration

Use `QuantumECCConfig` for centralized configuration:

```python
from config import QuantumECCConfig

config = QuantumECCConfig(
    initial_state='0',
    num_physical_qubits=4,
    error_threshold=0.5,
    max_correction_attempts=3,
    enable_logging=True
)

# Validate configuration
config.validate()

# Load from dictionary
config_dict = {
    'initial_state': '1',
    'error_threshold': 0.7,
}
config = QuantumECCConfig.from_dict(config_dict)
```

## Testing

Comprehensive test suite with 30+ test cases covering:
- Valid state initialization
- Error detection and correction
- Encoding and decoding
- Syndrome measurements
- Exception handling
- Metrics tracking

### Run Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests with coverage
pytest test_quantum_ecc.py -v --cov=quantum_ecc

# Run specific test class
pytest test_quantum_ecc.py::TestQuantumBit -v

# Run with detailed output
pytest test_quantum_ecc.py -vv --tb=short
```

## Design Philosophy

### 1. Separation of Concerns
- `QuantumBit`: State management
- `QuantumErrorCorrection`: Error correction logic
- `ErrorModel`: Error simulation (abstract, extensible)
- `SyndromeResult`: Measurement results
- `QuantumMetrics`: Operational metrics

### 2. Type Safety
- Full type hints on all functions
- Enum for quantum states (prevents invalid values)
- Dataclass for structured results

### 3. Testability
- Pure functions where possible
- Dependency injection (error_model parameter)
- Fixtures for test setup
- Parametrized tests for multiple cases

### 4. Error Handling
- Custom exception hierarchy with meaningful names
- Input validation with clear error messages
- Graceful degradation where possible

### 5. Observability
- Comprehensive logging at debug/info levels
- QuantumMetrics for tracking operations
- Error history per qubit
- Detailed exception messages

## Production Considerations

### Logging
Enable logging to track QEC operations:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Metrics Collection
Track QEC statistics for monitoring:

```python
qec = QuantumErrorCorrection(qbit)
qec.encode()
syndrome = qec.measure_syndrome()
qec.correct(syndrome)
qec.decode()

metrics = qec.get_metrics()
print(f"Success rate: {metrics.errors_corrected / metrics.errors_detected * 100:.1f}%")
```

### Performance
- O(1) encoding: Fixed 4 physical qubits
- O(4) syndrome measurement: Parity checks on physical qubits
- O(4) correction: Apply recovery operations
- O(4) decoding: Majority voting on physical qubits

## Future Enhancements

- [ ] Surface code implementation
- [ ] Topological codes
- [ ] Integration with Qiskit backends
- [ ] Benchmarking utilities
- [ ] Real-time monitoring dashboard
- [ ] Advanced error models (depolarizing, amplitude damping)

## References

- Knill, E., et al. (2000). "Towards Fault-Tolerant Quantum Computing with Trapped Ions"
- Surface codes: Towards practical large-scale quantum computation
- [[n,k,d]] codes notation: n physical qubits, k logical qubits, distance d

## License

MIT License
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

Built with harmonic geometry and quantum error correction principles.
