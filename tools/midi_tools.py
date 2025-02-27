from smolagents import Tool
import mido
import sys
import os

# Add parent directory to sys.path to import midi_loop
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from midi_loop import MidiEventLoop

class MidiSequenceTool(Tool):
    
    def __init__(self, midi_loop=None):
        """
        Initialize the MidiSequenceTool.
        
        Args:
            midi_loop: MidiEventLoop instance to send notes to
        """
        super().__init__()
        self.midi_loop = midi_loop
        self.default_channel = 0  # Default MIDI channel (0-15)
        self.output_device = None  # Selected output device from UI
    
    def set_midi_loop(self, midi_loop):
        """
        Set the MIDI event loop to send notes to.
        
        Args:
            midi_loop: MidiEventLoop instance
        """
        self.midi_loop = midi_loop
    
    def set_output_device(self, device_name):
        """
        Set the MIDI output device to use.
        
        Args:
            device_name: Name of the MIDI output device to use
        """
        self.output_device = None if device_name == "None" else device_name
    
    def forward(self, notes, num_bars=1, channel=None, quantize=True):
        """
        Send a sequence of MIDI notes to be spread across the specified number of bars.
        
        Args:
            notes: List of MIDI note numbers or dictionaries with note, velocity, etc.
            num_bars: Number of bars to spread the notes across
            channel: MIDI channel to use for the notes
            quantize: Whether to quantize the notes to the MIDI clock
            
        Returns:
            A string indicating the result of the operation
        """
        if channel is None:
            channel = self.default_channel
        
        if self.midi_loop is None:
            return "Error: MIDI event loop not initialized"
        
        try:
            # Validate inputs
            if not isinstance(notes, list):
                return "Error: Notes must be a list of note numbers or dictionaries"
            
            if len(notes) == 0:
                return "Error: Notes list is empty"
            
            num_bars = int(num_bars)
            if num_bars <= 0:
                return f"Error: Number of bars {num_bars} must be positive"
            
            channel = int(channel)
            if channel < 0 or channel > 15:
                return f"Error: Channel value {channel} is out of range (0-15)"
            
            # Check if MIDI clock is present
            midi_clock_status = "using internal clock"
            if self.midi_loop.midi_clock_present:
                midi_clock_status = "synchronized to external MIDI clock"
            
            # Validate and process each note
            processed_notes = []
            for i, note_data in enumerate(notes):
                if isinstance(note_data, (int, float)):
                    note = int(note_data)
                    if note < 0 or note > 127:
                        return f"Error: Note value {note} at position {i} is out of range (0-127)"
                    processed_notes.append(note)
                elif isinstance(note_data, dict):
                    if 'note' not in note_data:
                        return f"Error: Note dictionary at position {i} is missing 'note' field"
                    
                    note = int(note_data['note'])
                    if note < 0 or note > 127:
                        return f"Error: Note value {note} at position {i} is out of range (0-127)"
                    
                    if 'velocity' in note_data:
                        velocity = int(note_data['velocity'])
                        if velocity < 0 or velocity > 127:
                            return f"Error: Velocity value {velocity} at position {i} is out of range (0-127)"
                    
                    processed_notes.append(note_data)
                elif isinstance(note_data, list):
                    # This is a chord
                    chord_notes = []
                    for j, chord_note in enumerate(note_data):
                        if isinstance(chord_note, (int, float)):
                            note = int(chord_note)
                            if note < 0 or note > 127:
                                return f"Error: Note value {note} in chord at position {i} is out of range (0-127)"
                            chord_notes.append(note)
                        else:
                            return f"Error: Invalid note in chord at position {i}, note {j}: {chord_note}"
                    processed_notes.append(chord_notes)
                else:
                    return f"Error: Invalid note data at position {i}: {note_data}"
            
            # Send the sequence to the MIDI event loop with the selected output device
            self.midi_loop.receive_notes_sequence(
                processed_notes, 
                num_bars, 
                channel, 
                quantize, 
                output_device=self.output_device
            )
            
            # Create a concise result message
            note_count = len(processed_notes)
            tempo_info = f" at {self.midi_loop.current_tempo:.1f} BPM"
            
            if all(isinstance(n, (int, float)) for n in processed_notes):
                return f"Sent {note_count} notes across {num_bars} bars on channel {channel}{tempo_info} ({midi_clock_status})"
            elif all(isinstance(n, list) for n in processed_notes):
                chord_count = sum(len(chord) for chord in processed_notes if isinstance(chord, list))
                return f"Sent {note_count} chords ({chord_count} total notes) across {num_bars} bars on channel {channel}{tempo_info} ({midi_clock_status})"
            else:
                return f"Sent sequence of {note_count} MIDI events across {num_bars} bars on channel {channel}{tempo_info} ({midi_clock_status})"
                   
        except Exception as e:
            return f"Error sending MIDI sequence: {str(e)}"
    
    @property
    def name(self):
        return "send_midi_sequence"
    
    @property
    def description(self):
        return """Send a sequence of MIDI notes to be spread across a specified number of bars.

This tool allows you to send musical patterns as sequences of MIDI notes that will be automatically distributed evenly across a specified number of bars.

MIDI Notes Reference:
- Middle C is note number 60
- Each semitone up/down is +/- 1 (e.g., C# is 61, B is 59)
- Full octave is +/- 12 notes
- Range: 0-127 (C-1 to G9)

Common Notes:
- C4 (Middle C): 60
- D4: 62
- E4: 64
- F4: 65
- G4: 67
- A4: 69
- B4: 71
- C5: 72

Examples:

1. Basic C Major Scale (simple note numbers):
```python
send_midi_sequence(notes=[60, 62, 64, 65, 67, 69, 71, 72], num_bars=1)
```

2. C Major Chord Arpeggio (C-E-G-C):
```python
send_midi_sequence(notes=[60, 64, 67, 72], num_bars=1)
```

3. C Minor Chord Arpeggio (C-Eb-G-C):
```python
send_midi_sequence(notes=[60, 63, 67, 72], num_bars=1)
```

4. Notes with varying velocities (loudness):
```python
send_midi_sequence(notes=[
    {'note': 60, 'velocity': 100},  # C4 loud
    {'note': 64, 'velocity': 64},   # E4 medium
    {'note': 67, 'velocity': 32},   # G4 soft
    {'note': 72, 'velocity': 127}   # C5 very loud
], num_bars=1)
```

5. Complex rhythm pattern with custom durations:
```python
send_midi_sequence(notes=[
    {'note': 60, 'velocity': 100, 'duration': 0.5},  # C4 with longer duration
    {'note': 62, 'velocity': 80, 'duration': 0.25},  # D4 with shorter duration
    {'note': 64, 'velocity': 90, 'duration': 0.5},   # E4 with longer duration
    {'note': 65, 'velocity': 70, 'duration': 0.25},  # F4 with shorter duration
    {'note': 67, 'velocity': 100, 'duration': 1.0}   # G4 with longest duration
], num_bars=2)
```

6. Melody spread across 4 bars:
```python
send_midi_sequence(notes=[60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62, 60], num_bars=4)
```

7. Using a different MIDI channel (e.g., for different instruments):
```python
send_midi_sequence(notes=[60, 64, 67, 72], num_bars=1, channel=2)
```

8. Common chord progressions (C-F-G-C in root position):
```python
send_midi_sequence(notes=[
    [60, 64, 67],  # C major
    [65, 69, 72],  # F major
    [67, 71, 74],  # G major
    [60, 64, 67]   # C major
], num_bars=4)
```

Note: The notes will be distributed evenly across the specified number of bars. If you want more precise timing control, consider using more detailed note dictionaries with duration values.
"""
    
    @property
    def inputs(self):
        return {
            "notes": {
                "type": "array",
                "description": "List of MIDI note numbers (0-127) or dictionaries with note, velocity, etc.",
                "required": True
            },
            "num_bars": {
                "type": "number",
                "description": "Number of bars to spread the notes across",
                "default": 1,
                "nullable": True
            },
            "channel": {
                "type": "number",
                "description": "MIDI channel to use (0-15)",
                "default": "1",
                "nullable": True
            },
            "quantize": {
                "type": "boolean",
                "description": "Whether to quantize the notes to the MIDI clock",
                "default": True,
                "nullable": True
            }
        }
    
    @property
    def output_type(self):
        return "string"
