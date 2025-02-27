import mido
import threading
import time
import queue
from typing import Optional, List, Dict, Any

class MidiEventLoop:
    """
    A MIDI event loop that can receive notes from an agent, sync to MIDI clock,
    and play notes to a default output port.
    """
    def __init__(self, default_tempo=120, time_signature=(4, 4)):
        """
        Initialize the MIDI event loop.
        
        Args:
            default_tempo: Default tempo in BPM if no MIDI clock is present
            time_signature: Time signature as a tuple (numerator, denominator)
        """
        self.default_tempo = default_tempo
        self.current_tempo = default_tempo
        self.time_signature = time_signature
        self.running = False
        self.note_queue = queue.Queue()
        self.loop_notes = []
        self.midi_clock_present = False
        self.tick_counter = 0
        self.ppq = 24  # Pulses per quarter note (standard MIDI clock)
        self.last_tick_time = None
        self.current_bar = 0
        self.ticks_per_bar = self.ppq * self.time_signature[0]  # Ticks per bar
        
        # Try to open MIDI ports
        try:
            available_inputs = mido.get_input_names()
            available_outputs = mido.get_output_names()
            
            print(f"Available MIDI inputs: {available_inputs}")
            print(f"Available MIDI outputs: {available_outputs}")
            
            if available_inputs:
                self.input_port = mido.open_input(available_inputs[0], callback=self._handle_midi_message)
                print(f"Connected to MIDI input: {available_inputs[0]}")
            else:
                self.input_port = None
                print("No MIDI input ports available")
            
            if available_outputs:
                self.output_port = mido.open_output(available_outputs[0])
                print(f"Connected to MIDI output: {available_outputs[0]}")
            else:
                self.output_port = None
                print("No MIDI output ports available")
                
        except Exception as e:
            print(f"Error setting up MIDI ports: {e}")
            self.input_port = None
            self.output_port = None
    
    def _handle_midi_message(self, message):
        """
        Handle incoming MIDI messages.
        
        Args:
            message: MIDI message to handle
        """
        # Handle MIDI clock messages
        if message.type == 'clock':
            self.midi_clock_present = True
            self._process_clock_tick()
        
        # Handle MIDI start/stop/continue messages
        elif message.type == 'start':
            self.tick_counter = 0
            self.current_bar = 0
            self.running = True
        elif message.type == 'stop':
            self.running = False
        elif message.type == 'continue':
            self.running = True
    
    def _process_clock_tick(self):
        """Process a single MIDI clock tick."""
        current_time = time.time()
        self.tick_counter += 1
        
        # Calculate tempo from MIDI clock if we have received enough ticks
        if self.tick_counter % self.ppq == 0 and self.last_tick_time is not None:
            # Calculate time for a quarter note (24 MIDI clock ticks)
            quarter_note_time = (current_time - self.last_tick_time) * self.ppq
            if quarter_note_time > 0:
                # Convert to BPM (60 seconds / quarter_note_time)
                self.current_tempo = 60.0 / quarter_note_time
                print(f"Current tempo: {self.current_tempo:.1f} BPM")
            
            self.last_tick_time = current_time
        
        # Check if we've completed a bar
        if self.tick_counter % self.ticks_per_bar == 0:
            self.current_bar += 1
            print(f"Bar {self.current_bar}")
        
        # Every quarter note (24 ticks), check if we need to play notes
        if self.tick_counter % self.ppq == 0:
            self._play_scheduled_notes()
    
    def _play_scheduled_notes(self):
        """Play any notes that are scheduled to be played."""
        if not self.running or not self.output_port:
            return
        
        # Play all notes in the loop
        for note in self.loop_notes:
            # Clone the message to avoid modifying the original
            if isinstance(note, mido.Message):
                self.output_port.send(note.copy())
    
    def add_note_to_loop(self, note):
        """
        Add a note to the loop.
        
        Args:
            note: MIDI note message to add to the loop
        """
        if isinstance(note, mido.Message):
            self.loop_notes.append(note)
        else:
            print(f"Warning: Tried to add invalid MIDI message to loop: {note}")
    
    def clear_loop(self):
        """Clear all notes from the loop."""
        self.loop_notes = []
    
    def start(self):
        """Start the MIDI event loop."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("MIDI event loop started")
    
    def stop(self):
        """Stop the MIDI event loop."""
        self.running = False
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        
        # Close MIDI ports
        if self.input_port:
            self.input_port.close()
        if self.output_port:
            self.output_port.close()
        
        print("MIDI event loop stopped")
    
    def _run_loop(self):
        """Main loop function that runs in a separate thread."""
        self.last_tick_time = time.time()
        
        while self.running:
            # If we're not receiving MIDI clock, generate our own timing
            if not self.midi_clock_present:
                # Calculate sleep time based on tempo (quarter note duration)
                sleep_time = 60.0 / self.default_tempo
                time.sleep(sleep_time)
                self._play_scheduled_notes()
            else:
                # If we have MIDI clock, just sleep a bit to avoid busy waiting
                time.sleep(0.001)
            
            # Process any new notes from the agent
            try:
                while not self.note_queue.empty():
                    note = self.note_queue.get_nowait()
                    self.add_note_to_loop(note)
                    self.note_queue.task_done()
            except queue.Empty:
                pass
    
    def receive_notes_sequence(self, notes, num_bars=1, channel=0):
        """
        Receive a sequence of notes from the agent and distribute them across the specified number of bars.
        
        Args:
            notes: List of note dictionaries, MIDI note numbers, or lists of notes (for chords)
            num_bars: Number of bars to distribute the notes across
            channel: MIDI channel to use for the notes
        """
        if not notes:
            print("Warning: Received empty notes sequence")
            return
        
        # Calculate the total number of beats in the specified bars
        beats_per_bar = self.time_signature[0]
        total_beats = beats_per_bar * num_bars
        
        # Calculate time intervals between notes
        num_notes = len(notes)
        interval = total_beats / num_notes
        
        # Clear existing loop if any
        self.clear_loop()
        
        # Process each note or chord
        for i, note_data in enumerate(notes):
            # Calculate the position of this note in beats
            position_in_beats = i * interval
            
            # Handle different types of note data
            if isinstance(note_data, list):
                # This is a chord (list of notes to be played simultaneously)
                for chord_note in note_data:
                    self._process_single_note(chord_note, channel, interval)
            elif isinstance(note_data, (int, float)):
                # This is a single note number
                self._process_single_note(note_data, channel, interval)
            elif isinstance(note_data, dict):
                # This is a note dictionary
                self._process_single_note(note_data, channel, interval)
            else:
                print(f"Warning: Invalid note data in sequence: {note_data}")
        
        print(f"Added {num_notes} note events distributed across {num_bars} bars to the loop")
    
    def _process_single_note(self, note_data, channel, interval):
        """
        Process a single note and add it to the loop.
        
        Args:
            note_data: Note data (number or dictionary)
            channel: MIDI channel to use
            interval: Time interval for note duration
        """
        # If note_data is just a number, convert it to a dictionary
        if isinstance(note_data, (int, float)):
            note_data = {'note': int(note_data), 'velocity': 64}
        
        # Ensure note_data is a dictionary
        if isinstance(note_data, dict):
            # Create note_on message
            note_on = mido.Message('note_on',
                                  note=note_data.get('note', 60),
                                  velocity=note_data.get('velocity', 64),
                                  channel=note_data.get('channel', channel))
            
            # Add note_on to the loop
            self.add_note_to_loop(note_on)
            
            # Create note_off message (default duration is 80% of the interval)
            duration = note_data.get('duration', interval * 0.8)
            note_off = mido.Message('note_off',
                                   note=note_data.get('note', 60),
                                   velocity=0,
                                   channel=note_data.get('channel', channel))
            
            # Add note_off to the loop
            self.add_note_to_loop(note_off)
        else:
            print(f"Warning: Invalid note data: {note_data}")
