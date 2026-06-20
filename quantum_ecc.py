"""
Triny Error Correction Framework
Built on Platonic Solid Architecture and Harmonic Resonance Principles

The framework organizes trinary error correction through geometric structure:
- Tetrahedron (4): Foundation - locked trinary substrate (-1, 0, +1)
- Cube (6): Stabilization - 6 error states representing harmonic disruptions
- Octahedron (3-6): Bridge - detection of polarity and frequency deviations
- Dodecahedron (9): Transformation - 9-parameter restoration to trinary poles
- Icosahedron (9+vortex): Flow - recursive vortex rebalancing

Triny state representation uses angle/phase mapping:
- -1 pole: 30° (π/6) — 3-frequency foundation
- 0 pole (neutral/center): 60° (π/3) — 6-frequency bridge
- +1 pole: 90° (π/2) — 9-frequency transformation

Errors are deviations from these three discrete poles.
"""

import numpy as np
from typing import List, Tuple, Dict
from enum import Enum


class TrinaryPole(Enum):
    """The three fundamental poles in trinary logic"""
    NEGATIVE = -1      # -1 pole at 30° (π/6, 3-frequency)
    NEUTRAL = 0        # 0 pole at 60° (π/3, 6-frequency)
    POSITIVE = 1       # +1 pole at 90° (π/2, 9-frequency)


class ErrorType(Enum):
    """Three distinct error types in trinary space"""
    POLARITY_INVERSION = 1      # State flips -1 ↔ +1 through 0, inverting harmonic sign
    FREQUENCY_SHIFT = 2         # Resonance drifts away from 3/6/9, creating beat frequency
    CENTER_DRIFT = 3            # State migrates toward/away from 0, or vortex spin reversal


class HarmonicGeometry:
    """Foundation mappings: 3-6-9 resonance to trinary poles and angles"""
    
    # 3-6-9 resonance ratios as fundamental organizing principles
    FUNDAMENTAL_RATIOS = {
        3: 0.333333,    # 1/3
        6: 0.666666,    # 2/3
        9: 1.0,         # complete resonance
    }
    
    # Trinary pole angles derived from 3-6-9 harmonics
    TRINARY_POLE_ANGLES = {
        TrinaryPole.NEGATIVE: np.pi / 6,      # 30° — 3-frequency foundation (-1)
        TrinaryPole.NEUTRAL: np.pi / 3,       # 60° — 6-frequency bridge (0)
        TrinaryPole.POSITIVE: np.pi / 2,      # 90° — 9-frequency transformation (+1)
    }
    
    # Platonic dimensions as quantum/trinary parameters
    PLATONIC_DIMENSIONS = {
        'tetrahedron': 4,      # 4 faces - trinary substrate (3 poles + 1 locked)
        'cube': 6,              # 6 faces - 6 error states
        'octahedron': 8,        # 8 vertices - 3 poles + 6 harmonic directions (3-6 bridge)
        'dodecahedron': 9,      # 9 rotational axes - 9-parameter restoration
        'icosahedron': 20,      # 20 faces - recursive vortex iterations
    }
    
    @staticmethod
    def get_pole_angle(pole: TrinaryPole) -> float:
        """Get the canonical angle for a trinary pole"""
        return HarmonicGeometry.TRINARY_POLE_ANGLES[pole]
    
    @staticmethod
    def pole_from_angle(angle: float, tolerance: float = 0.1) -> TrinaryPole:
        """Determine which trinary pole an angle is closest to"""
        angles = {
            TrinaryPole.NEGATIVE: np.pi / 6,
            TrinaryPole.NEUTRAL: np.pi / 3,
            TrinaryPole.POSITIVE: np.pi / 2,
        }
        
        # Normalize angle to [0, π]
        angle_norm = angle % np.pi
        
        # Find closest pole
        distances = {pole: abs(angle_norm - ang) for pole, ang in angles.items()}
        closest_pole = min(distances, key=distances.get)
        
        if distances[closest_pole] <= tolerance:
            return closest_pole
        return None  # Indicates error state (deviation from pole)
    
    @staticmethod
    def detect_frequency_shift(angle: float, pole: TrinaryPole) -> float:
        """Measure harmonic beat frequency (deviation from intended pole)"""
        pole_angle = HarmonicGeometry.get_pole_angle(pole)
        angle_norm = angle % np.pi
        
        # Beat frequency is the angular deviation from the pole
        beat_frequency = abs(angle_norm - pole_angle)
        return beat_frequency
    
    @staticmethod
    def harmonic_restoration_angle(error_type: ErrorType, current_angle: float, 
                                   target_pole: TrinaryPole) -> float:
        """Calculate restoration angle to pull state back to target pole"""
        target_angle = HarmonicGeometry.get_pole_angle(target_pole)
        current_normalized = current_angle % np.pi
        
        if error_type == ErrorType.POLARITY_INVERSION:
            # Flip through the neutral pole
            return (np.pi - current_normalized) % np.pi
        elif error_type == ErrorType.FREQUENCY_SHIFT:
            # Direct rotation to target pole
            return target_angle
        elif error_type == ErrorType.CENTER_DRIFT:
            # Spiral correction through harmonic rebalancing
            return (target_angle + current_normalized) / 2
        
        return target_angle


class TrinaryState:
    """Represents a single trinary state with its pole and harmonic properties"""
    
    def __init__(self, pole: TrinaryPole = TrinaryPole.NEUTRAL, angle: float = None):
        """
        Initialize a trinary state.
        
        Args:
            pole: The current trinary pole (-1, 0, or +1)
            angle: Optional explicit angle; if not provided, use pole's canonical angle
        """
        self.pole = pole
        self.angle = angle if angle is not None else HarmonicGeometry.get_pole_angle(pole)
        self.error_type = None
        self.beat_frequency = 0.0
    
    def detect_error(self) -> Tuple[bool, ErrorType]:
        """
        Detect if this state has deviated from its intended pole.
        
        Returns:
            (has_error, error_type)
        """
        detected_pole = HarmonicGeometry.pole_from_angle(self.angle)
        
        if detected_pole is None:
            # State is off a pole—determine error type
            beat_freq = HarmonicGeometry.detect_frequency_shift(self.angle, self.pole)
            self.beat_frequency = beat_freq
            
            # Classify error based on angular deviation
            if self.angle > np.pi / 2 + 0.2:  # Beyond +1 pole
                self.error_type = ErrorType.POLARITY_INVERSION
                return True, ErrorType.POLARITY_INVERSION
            elif self.angle < np.pi / 6 - 0.2:  # Before -1 pole
                self.error_type = ErrorType.POLARITY_INVERSION
                return True, ErrorType.POLARITY_INVERSION
            elif abs(beat_freq) > 0.15:  # Significant frequency shift
                self.error_type = ErrorType.FREQUENCY_SHIFT
                return True, ErrorType.FREQUENCY_SHIFT
            else:
                self.error_type = ErrorType.CENTER_DRIFT
                return True, ErrorType.CENTER_DRIFT
        
        self.error_type = None
        self.beat_frequency = 0.0
        return False, None
    
    def restore(self, target_pole: TrinaryPole) -> None:
        """Restore state to target pole"""
        if self.error_type is not None:
            restoration_angle = HarmonicGeometry.harmonic_restoration_angle(
                self.error_type, self.angle, target_pole
            )
            self.angle = restoration_angle
            self.pole = target_pole
            self.error_type = None
            self.beat_frequency = 0.0
    
    def __repr__(self):
        angle_deg = np.degrees(self.angle % np.pi)
        return f"TrinaryState(pole={self.pole.name}, angle={angle_deg:.1f}°, beat_freq={self.beat_frequency:.3f})"


class Tetrahedron:
    """Foundation State - locked trinary substrate with 4 faces"""
    
    def __init__(self):
        self.name = "Tetrahedron (Foundation - Trinary Substrate)"
        self.n_faces = 4
        # 3 poles + 1 locked center
        self.states = [
            TrinaryState(TrinaryPole.NEGATIVE),
            TrinaryState(TrinaryPole.NEUTRAL),
            TrinaryState(TrinaryPole.POSITIVE),
            TrinaryState(TrinaryPole.NEUTRAL),  # Locked center face
        ]
    
    def lock_center(self) -> None:
        """Lock the center (neutral) state to prevent drift"""
        self.states[3].angle = HarmonicGeometry.get_pole_angle(TrinaryPole.NEUTRAL)
        self.states[3].error_type = None
    
    def initialize_logical_state(self, value: int) -> None:
        """Initialize the 3 pole faces to represent a logical state"""
        if value == -1:
            self.states[0].pole = TrinaryPole.NEGATIVE
            self.states[1].pole = TrinaryPole.NEGATIVE
            self.states[2].pole = TrinaryPole.NEGATIVE
        elif value == 0:
            self.states[0].pole = TrinaryPole.NEUTRAL
            self.states[1].pole = TrinaryPole.NEUTRAL
            self.states[2].pole = TrinaryPole.NEUTRAL
        elif value == 1:
            self.states[0].pole = TrinaryPole.POSITIVE
            self.states[1].pole = TrinaryPole.POSITIVE
            self.states[2].pole = TrinaryPole.POSITIVE
    
    def get_state_snapshot(self) -> Dict:
        """Return current state of all 4 faces"""
        return {f'face_{i}': str(state) for i, state in enumerate(self.states)}


class Cube:
    """Stabilization Layer - 6 error states representing harmonic disruptions"""
    
    def __init__(self, tetrahedron: Tetrahedron):
        self.tet = tetrahedron
        self.name = "Cube (Stabilization - 6 Error States)"
        self.n_faces = 6
        # 6 error states: 3 frequency-shifted + 3 polarity-inverted directions
        self.error_states = {
            'freq_shift_negative': ErrorType.FREQUENCY_SHIFT,
            'freq_shift_neutral': ErrorType.FREQUENCY_SHIFT,
            'freq_shift_positive': ErrorType.FREQUENCY_SHIFT,
            'polarity_inv_neg_to_pos': ErrorType.POLARITY_INVERSION,
            'polarity_inv_pos_to_neg': ErrorType.POLARITY_INVERSION,
            'center_drift': ErrorType.CENTER_DRIFT,
        }
    
    def stabilize(self) -> List[TrinaryState]:
        """Apply harmonic stabilization to tetrahedron states"""
        stabilized = []
        for state in self.tet.states:
            # Strengthen the state toward its intended pole
            target_pole = state.pole
            target_angle = HarmonicGeometry.get_pole_angle(target_pole)
            
            # Harmonic reinforcement: move 90% of the way to the target pole
            reinforced_angle = state.angle + 0.9 * (target_angle - state.angle)
            
            new_state = TrinaryState(target_pole, reinforced_angle)
            stabilized.append(new_state)
        
        return stabilized
    
    def get_stabilizer_generators(self) -> List[str]:
        """Return the 6 stabilizer generator definitions (harmonic basis)"""
        return [
            "3-FREQ-NEG",   # Stabilizer 1: 3-frequency on -1 pole
            "3-FREQ-NEUT",  # Stabilizer 2: 3-frequency on 0 pole
            "3-FREQ-POS",   # Stabilizer 3: 3-frequency on +1 pole
            "6-FREQ-NEG",   # Stabilizer 4: 6-frequency on -1 pole
            "6-FREQ-NEUT",  # Stabilizer 5: 6-frequency on 0 pole
            "6-FREQ-POS",   # Stabilizer 6: 6-frequency on +1 pole
        ]


class Octahedron:
    """Syndrome Detection Bridge - 3-6 harmonic measurement and error detection"""
    
    def __init__(self, cube: Cube):
        self.cube = cube
        self.name = "Octahedron (Detection Bridge - 3-6 Harmonic)"
        self.n_vertices = 8
        # 3 poles + 6 harmonic deviation directions
        self.poles = [TrinaryPole.NEGATIVE, TrinaryPole.NEUTRAL, TrinaryPole.POSITIVE]
        self.harmonic_directions = [
            'freq_shift', 'polarity_inversion', 'center_drift',  # 3 primary directions
            'freq_shift_strong', 'polarity_inv_strong', 'center_drift_strong'  # 3 strong directions
        ]
    
    def measure_syndromes(self, states: List[TrinaryState]) -> Dict:
        """Measure syndrome pattern for all states"""
        syndromes = {}
        
        for i, state in enumerate(states):
            has_error, error_type = state.detect_error()
            syndromes[f'state_{i}'] = {
                'has_error': has_error,
                'error_type': error_type.name if error_type else 'NONE',
                'beat_frequency': state.beat_frequency,
                'current_angle': state.angle,
                'pole': state.pole.name,
            }
        
        return syndromes
    
    def decode_syndrome(self, syndromes: Dict) -> Dict:
        """Decode syndromes to correction instructions"""
        corrections = {}
        
        for state_id, syndrome_data in syndromes.items():
            if syndrome_data['has_error']:
                error_type = syndrome_data['error_type']
                
                # Determine target pole based on current state
                current_pole = TrinaryPole[syndrome_data['pole']]
                
                # For polarity inversion, flip to opposite pole
                if error_type == 'POLARITY_INVERSION':
                    if current_pole == TrinaryPole.NEGATIVE:
                        target = TrinaryPole.POSITIVE
                    elif current_pole == TrinaryPole.POSITIVE:
                        target = TrinaryPole.NEGATIVE
                    else:
                        target = current_pole
                else:
                    # For frequency shift and center drift, stay at current pole
                    target = current_pole
                
                corrections[state_id] = {
                    'error_type': error_type,
                    'target_pole': target.name,
                    'current_angle': syndrome_data['current_angle'],
                    'beat_frequency': syndrome_data['beat_frequency'],
                }
        
        return corrections


class Dodecahedron:
    """Error Transformation - 9-parameter restoration to trinary poles"""
    
    def __init__(self, octahedron: Octahedron):
        self.octa = octahedron
        self.name = "Dodecahedron (Restoration - 9-Parameter)"
        self.n_axes = 9
        # 9 restoration parameters: 3 poles × 3 error types
        self.restoration_params = {
            'NEG_freq_shift': 0.111,
            'NEG_polarity': 0.222,
            'NEG_center_drift': 0.333,
            'NEUT_freq_shift': 0.444,
            'NEUT_polarity': 0.555,
            'NEUT_center_drift': 0.666,
            'POS_freq_shift': 0.777,
            'POS_polarity': 0.888,
            'POS_center_drift': 0.999,
        }
    
    def apply_restoration(self, states: List[TrinaryState], 
                         corrections: Dict) -> List[TrinaryState]:
        """Apply 9-parameter restoration to correct errors"""
        restored = [state for state in states]  # Copy
        
        for state_idx, correction in corrections.items():
            idx = int(state_idx.split('_')[1])
            error_type = correction['error_type']
            target_pole = TrinaryPole[correction['target_pole']]
            
            # Apply harmonic restoration
            restored[idx].restore(target_pole)
        
        return restored
    
    def get_restoration_matrix(self) -> Dict:
        """Return the 9-parameter restoration transformation matrix"""
        return self.restoration_params


class Icosahedron:
    """Recursive Vortex Flow - recursive spiral rebalancing through harmonic resonance"""
    
    def __init__(self, dodecahedron: Dodecahedron):
        self.dodeca = dodecahedron
        self.name = "Icosahedron (Recursive Vortex - 9+Spiral)"
        self.n_faces = 20
        self.vortex_iterations = 3
    
    def apply_vortex_correction(self, states: List[TrinaryState], 
                               iterations: int = None) -> List[TrinaryState]:
        """
        Apply recursive vortex flow: spiral through harmonic rebalancing.
        
        Each iteration applies 9-parameter angles in rotating spiral pattern,
        converging back toward the three trinary poles.
        """
        if iterations is None:
            iterations = self.vortex_iterations
        
        vortex_states = [state for state in states]  # Copy
        
        for iteration in range(iterations):
            for state_idx, state in enumerate(vortex_states):
                # Calculate spiral angle based on iteration and state index
                spiral_phase = (iteration * np.pi / 3) + (state_idx * np.pi / 9)
                
                # Apply harmonic spiral: rotate toward nearest pole
                nearest_pole = HarmonicGeometry.pole_from_angle(state.angle)
                if nearest_pole is None:
                    # If off-pole, calculate which pole is nearest
                    distances = {
                        TrinaryPole.NEGATIVE: abs(state.angle - np.pi / 6),
                        TrinaryPole.NEUTRAL: abs(state.angle - np.pi / 3),
                        TrinaryPole.POSITIVE: abs(state.angle - np.pi / 2),
                    }
                    nearest_pole = min(distances, key=distances.get)
                
                target_angle = HarmonicGeometry.get_pole_angle(nearest_pole)
                
                # Spiral convergence: move toward target with decreasing step size
                convergence_factor = 1.0 / (iteration + 2)
                new_angle = state.angle + convergence_factor * (target_angle - state.angle)
                
                vortex_states[state_idx].angle = new_angle
                vortex_states[state_idx].pole = nearest_pole
        
        return vortex_states


class TrinaryErrorCorrectionCodex:
    """Complete framework: Tetrahedron through Icosahedron for trinary error correction"""
    
    def __init__(self):
        self.tet = Tetrahedron()
        self.cube = Cube(self.tet)
        self.octa = Octahedron(self.cube)
        self.dodeca = Dodecahedron(self.octa)
        self.icosa = Icosahedron(self.dodeca)
        self.name = "Trinary Error Correction Codex (Harmonic Geometry)"
    
    def initialize(self, logical_value: int) -> None:
        """Initialize the framework to a logical state (-1, 0, or +1)"""
        self.tet.initialize_logical_state(logical_value)
        self.tet.lock_center()
    
    def inject_error(self, state_index: int, error_type: ErrorType, 
                    magnitude: float = 0.2) -> None:
        """Inject an error into a specific state"""
        state = self.tet.states[state_index]
        
        if error_type == ErrorType.POLARITY_INVERSION:
            # Flip to opposite pole
            if state.pole == TrinaryPole.NEGATIVE:
                state.angle = np.pi / 2
                state.pole = TrinaryPole.POSITIVE
            elif state.pole == TrinaryPole.POSITIVE:
                state.angle = np.pi / 6
                state.pole = TrinaryPole.NEGATIVE
        elif error_type == ErrorType.FREQUENCY_SHIFT:
            # Shift angle away from pole
            state.angle += magnitude
        elif error_type == ErrorType.CENTER_DRIFT:
            # Drift toward neutral pole
            neutral_angle = np.pi / 3
            state.angle = state.angle + magnitude * (neutral_angle - state.angle)
    
    def measure_and_detect(self) -> Dict:
        """Measure syndromes and detect errors"""
        # Apply stabilization
        stabilized = self.cube.stabilize()
        
        # Measure syndromes
        syndromes = self.octa.measure_syndromes(stabilized)
        
        return {
            'syndromes': syndromes,
            'stabilizers': self.cube.get_stabilizer_generators(),
        }
    
    def correct_and_rebalance(self) -> Dict:
        """Full correction cycle: detect → decode → restore → vortex rebalance"""
        # Detect errors
        measurement = self.measure_and_detect()
        syndromes = measurement['syndromes']
        
        # Decode syndromes to corrections
        corrections = self.octa.decode_syndrome(syndromes)
        
        # Apply 9-parameter restoration
        restored = self.dodeca.apply_restoration(self.tet.states, corrections)
        self.tet.states = restored
        
        # Apply recursive vortex rebalancing
        vortex_corrected = self.icosa.apply_vortex_correction(self.tet.states)
        self.tet.states = vortex_corrected
        
        # Lock center again
        self.tet.lock_center()
        
        return {
            'syndromes': syndromes,
            'corrections': corrections,
            'final_states': self.tet.get_state_snapshot(),
        }
    
    def run_full_cycle(self, logical_value: int, 
                      error_state_index: int = None,
                      error_type: ErrorType = None) -> Dict:
        """Complete cycle: initialize → inject error (optional) → detect → correct → rebalance"""
        # Initialize
        self.initialize(logical_value)
        
        # Optionally inject error
        if error_state_index is not None and error_type is not None:
            self.inject_error(error_state_index, error_type)
        
        # Measure and detect
        measurement = self.measure_and_detect()
        
        # Correct and rebalance
        correction = self.correct_and_rebalance()
        
        return {
            'logical_value': logical_value,
            'error_injected': error_type.name if error_type else 'NONE',
            'measurement': measurement,
            'correction': correction,
            'framework_state': {
                'tetrahedron': self.tet.get_state_snapshot(),
            }
        }


if __name__ == '__main__':
    codex = TrinaryErrorCorrectionCodex()
    
    print("=" * 70)
    print("Trinary Error Correction Codex - Harmonic Geometry Framework")
    print("=" * 70)
    print()
    
    # Example 1: Initialize to +1, inject frequency shift error, correct
    print("Example 1: Logical +1 with Frequency Shift Error")
    print("-" * 70)
    result = codex.run_full_cycle(
        logical_value=1,
        error_state_index=0,
        error_type=ErrorType.FREQUENCY_SHIFT
    )
    
    print(f"Logical Value: {result['logical_value']}")
    print(f"Error Injected: {result['error_injected']}")
    print()
    print("Initial States:")
    for state_id, state_str in result['framework_state']['tetrahedron'].items():
        print(f"  {state_id}: {state_str}")
    print()
    print("Syndromes Detected:")
    for state_id, syndrome in result['measurement']['syndromes'].items():
        print(f"  {state_id}: error={syndrome['has_error']}, type={syndrome['error_type']}")
    print()
    print("Final States After Correction:")
    for state_id, state_str in result['correction']['final_states'].items():
        print(f"  {state_id}: {state_str}")
    print()
    print()
    
    # Example 2: Initialize to -1, inject polarity inversion, correct
    print("Example 2: Logical -1 with Polarity Inversion Error")
    print("-" * 70)
    codex2 = TrinaryErrorCorrectionCodex()
    result2 = codex2.run_full_cycle(
        logical_value=-1,
        error_state_index=1,
        error_type=ErrorType.POLARITY_INVERSION
    )
    
    print(f"Logical Value: {result2['logical_value']}")
    print(f"Error Injected: {result2['error_injected']}")
    print()
    print("Syndromes Detected:")
    for state_id, syndrome in result2['measurement']['syndromes'].items():
        print(f"  {state_id}: error={syndrome['has_error']}, type={syndrome['error_type']}")
    print()
    print("Stabilizer Generators:")
    for stab in result2['measurement']['stabilizers']:
        print(f"  {stab}")
    print()
    print("Framework Architecture:")
    print("  Tetrahedron (4) → Foundation (Trinary Substrate)")
    print("  Cube (6)        → Stabilization (6 Error States)")
    print("  Octahedron (3-6) → Detection Bridge (3-6 Harmonic)")
    print("  Dodecahedron (9) → Restoration (9-Parameter)")
    print("  Icosahedron (9+vortex) → Vortex Rebalancing (Recursive Spiral)")
