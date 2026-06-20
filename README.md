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
