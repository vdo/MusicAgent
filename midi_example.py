import time
import mido
from midi_loop import MidiEventLoop

def select_midi_device(available_devices, device_type="input"):
    """
    Allow the user to select a MIDI device from a list of available devices.
    
    Args:
        available_devices: List of available MIDI device names
        device_type: Type of device (input or output)
        
    Returns:
        Selected device name or None if no devices are available
    """
    if not available_devices:
        print(f"No MIDI {device_type} devices available.")
        return None
    
    print(f"\nAvailable MIDI {device_type} devices:")
    for i, device in enumerate(available_devices):
        print(f"{i+1}. {device}")
    
    while True:
        try:
            selection = input(f"Select MIDI {device_type} device (1-{len(available_devices)}, or 0 for none): ")
            selection = int(selection.strip())
            
            if selection == 0:
                return None
            elif 1 <= selection <= len(available_devices):
                selected_device = available_devices[selection-1]
                print(f"Selected MIDI {device_type}: {selected_device}")
                return selected_device
            else:
                print(f"Please enter a number between 0 and {len(available_devices)}")
        except ValueError:
            print("Please enter a valid number")

def main():
    """
    Example script demonstrating how to use the MIDI event loop.
    """
    # Get available MIDI devices
    available_inputs = mido.get_input_names()
    available_outputs = mido.get_output_names()

    # Let the user select MIDI input and output devices
    print("\n=== MIDI Device Selection ===")
    selected_input = select_midi_device(available_inputs, "input")
    selected_output = select_midi_device(available_outputs, "output")
    
    # Create a MIDI event loop with default tempo of 120 BPM and 4/4 time signature
    # Don't automatically open ports
    midi_loop = MidiEventLoop(default_tempo=120, time_signature=(4, 4), auto_open_ports=False)
    
    # Manually set the input and output ports based on user selection
    # Open the selected input port
    if selected_input:
        try:
            midi_loop.input_port = mido.open_input(selected_input, callback=midi_loop._handle_midi_message)
            print(f"Connected to MIDI input: {selected_input}")
        except Exception as e:
            print(f"Error connecting to MIDI input {selected_input}: {e}")
            midi_loop.input_port = None
    else:
        midi_loop.input_port = None
        print("No MIDI input selected")

    # Open the selected output port
    if selected_output:
        try:
            midi_loop.output_port = mido.open_output(selected_output)
            print(f"Connected to MIDI output: {selected_output}")
        except Exception as e:
            print(f"Error connecting to MIDI output {selected_output}: {e}")
            midi_loop.output_port = None
    else:
        midi_loop.output_port = None
        print("No MIDI output selected")
    
    # Start the event loop
    midi_loop.start()
    
    try:
        # Demonstrate the sequence functionality
        print("Demonstrating MIDI sequence functionality...")
        
        # Example 1: Simple sequence of note numbers spread across 2 bars
        c_major_scale = [60, 62, 64, 65, 67, 69, 71, 72]
        print("Example 1: Simple sequence of note numbers (C major scale) spread across 2 bars")
        midi_loop.receive_notes_sequence(c_major_scale, num_bars=2, channel=0)
        
        # Let it play for a while
        print("Playing for 10 seconds...")
        time.sleep(10)
        
        # Clear the loop
        print("Clearing loop...")
        midi_loop.clear_loop()
        
        # Example 2: Sequence of note dictionaries with different velocities
        print("Example 2: Sequence with varying velocities spread across 1 bar")
        note_sequence = [
            {'note': 60, 'velocity': 100},  # C4 loud
            {'note': 64, 'velocity': 64},   # E4 medium
            {'note': 67, 'velocity': 32},   # G4 soft
            {'note': 72, 'velocity': 127},  # C5 very loud
        ]
        midi_loop.receive_notes_sequence(note_sequence, num_bars=1, channel=0)
        
        # Let it play for a while
        print("Playing for 10 seconds...")
        time.sleep(10)
        
        # Clear the loop
        print("Clearing loop...")
        midi_loop.clear_loop()
        
        # Example 3: C minor arpeggio spread across 4 bars
        print("Example 3: C minor arpeggio spread across 4 bars")
        c_minor_arpeggio = [60, 63, 67, 72, 67, 63, 60]
        midi_loop.receive_notes_sequence(c_minor_arpeggio, num_bars=4, channel=0)
        
        # Let it play for a while
        print("Playing for 15 seconds...")
        time.sleep(15)
        
        # Clear the loop
        print("Clearing loop...")
        midi_loop.clear_loop()
        
        # Example 4: Complex rhythm pattern with custom durations
        print("Example 4: Complex rhythm pattern with custom durations")
        rhythm_pattern = [
            {'note': 60, 'velocity': 100, 'duration': 0.5},  # C4 with longer duration
            {'note': 62, 'velocity': 80, 'duration': 0.25},  # D4 with shorter duration
            {'note': 64, 'velocity': 90, 'duration': 0.5},   # E4 with longer duration
            {'note': 65, 'velocity': 70, 'duration': 0.25},  # F4 with shorter duration
            {'note': 67, 'velocity': 100, 'duration': 1.0},  # G4 with longest duration
        ]
        midi_loop.receive_notes_sequence(rhythm_pattern, num_bars=2, channel=0)
        
        # Let it play for a while
        print("Playing for 15 seconds...")
        time.sleep(15)
        
        # Clear the loop
        print("Clearing loop...")
        midi_loop.clear_loop()
        
        # Example 5: Chord progression (C-F-G-C in root position)
        print("Example 5: Common chord progression (C-F-G-C)")
        chord_progression = [
            [60, 64, 67],  # C major
            [65, 69, 72],  # F major
            [67, 71, 74],  # G major
            [60, 64, 67]   # C major
        ]
        midi_loop.receive_notes_sequence(chord_progression, num_bars=4, channel=0)
        
        # Let it play for a while
        print("Playing for 15 seconds...")
        time.sleep(15)
        
    finally:
        # Stop the MIDI event loop
        midi_loop.stop()

if __name__ == "__main__":
    main()
