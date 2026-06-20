"""Configuration management for quantum error correction.

Provides defaults and utilities for configuring QEC parameters.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class QuantumECCConfig:
    """Configuration for quantum error correction system.

    Attributes:
        initial_state: Initial quantum state ('0', '1', '+', '-').
        num_physical_qubits: Number of physical qubits for encoding (default 4).
        error_threshold: Probability threshold for error detection.
        max_correction_attempts: Maximum number of correction retries.
        enable_logging: Whether to enable detailed logging.
    """

    initial_state: str = "0"
    num_physical_qubits: int = 4
    error_threshold: float = 0.5
    max_correction_attempts: int = 3
    enable_logging: bool = True

    def validate(self) -> bool:
        """Validate configuration parameters.

        Returns:
            True if all parameters are valid.

        Raises:
            ValueError: If any parameter is invalid.
        """
        if self.initial_state not in ["0", "1", "+", "-"]:
            raise ValueError(
                f"Invalid initial_state '{self.initial_state}'. "
                "Must be one of: '0', '1', '+', '-'"
            )

        if self.num_physical_qubits < 3:
            raise ValueError(
                f"num_physical_qubits must be >= 3, got {self.num_physical_qubits}"
            )

        if not (0.0 <= self.error_threshold <= 1.0):
            raise ValueError(
                f"error_threshold must be in [0.0, 1.0], got {self.error_threshold}"
            )

        if self.max_correction_attempts < 1:
            raise ValueError(
                f"max_correction_attempts must be >= 1, got {self.max_correction_attempts}"
            )

        return True

    @classmethod
    def from_dict(cls, config_dict: dict) -> "QuantumECCConfig":
        """Create configuration from dictionary.

        Args:
            config_dict: Dictionary of configuration parameters.

        Returns:
            QuantumECCConfig instance.
        """
        return cls(**config_dict)
