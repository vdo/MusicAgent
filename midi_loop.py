import rtmidi
import threading
import time
import queue
import os
from typing import Optional, List, Dict, Any

class MidiEventLoop:
    """
    A MIDI event loop that can receive notes from an agent, sync to MIDI clock,
    and play notes to a default output port.
    """
    def __init__(self, default_tempo=120, time_signature=(4, 4), auto_open_ports=True, debug=None):
        """
        Initialize the MIDI event loop.
        
        Args:
            default_tempo: Default tempo in BPM if no MIDI clock is present
            time_signature: Time signature as a tuple (numerator, denominator)
            auto_open_ports: Whether to automatically open MIDI ports
            debug: Whether to print debug information like bar numbers and tempo changes.
                  If None, will use the DEBUG environment variable.
        """
        self.default_tempo = default_tempo
        self.current_tempo = default_tempo
        self.time_signature = time_signature
        self.running = False
        self.transport_playing = False  # Flag to track if transport is playing
        self.note_queue = queue.Queue()
        self.loop_notes = []
        self.active_notes = {}  # Dict to track currently active notes by (note, channel) tuple
        self.pending_note_offs = []  # List to track note_off messages that need to be sent
        self.played_note_events = set()  # Set to track note events that have been played using (type, note, time) tuples
        self.midi_clock_present = False
        self.tick_counter = 0
        self.ppq = 24  # Pulses per quarter note (standard MIDI clock)
        self.last_tick_time = None
        self.current_bar = 0
        self.ticks_per_bar = self.ppq * self.time_signature[0]  # Ticks per bar
        
        # For tempo detection
        self.clock_intervals = []  # List to store intervals between clock messages
        
        # Check environment variable if debug is None
        if debug is None:
            debug_env = os.environ.get('DEBUG', '').lower()
            self.debug = debug_env in ('true', '1', 'yes', 'y')
        else:
            self.debug = debug
            
        self.tempo_displayed = False
        
        # Initialize ports to None
        self.midiin = None
        self.midiout = None
        
        # Try to open MIDI ports if auto_open_ports is True
        if auto_open_ports:
            self._open_default_ports()
    
    def _open_default_ports(self):
        """Open the default MIDI input and output ports."""
        try:
            available_inputs = rtmidi.MidiIn().get_ports()
            available_outputs = rtmidi.MidiOut().get_ports()
            
            print(f"Available MIDI inputs: {available_inputs}")
            print(f"Available MIDI outputs: {available_outputs}")
            
            if available_inputs:
                self.midiin = rtmidi.MidiIn()
                self.midiin.open_port(0)
                # Set callback for incoming MIDI messages
                self.midiin.set_callback(self._midi_callback)
                # Don't ignore MIDI clock messages
                self.midiin.ignore_types(timing=False)
                print(f"Connected to MIDI input: {available_inputs[0]}")
            else:
                self.midiin = None
                print("No MIDI input ports available")
            
            if available_outputs:
                self.midiout = rtmidi.MidiOut()
                self.midiout.open_port(0)
                print(f"Connected to MIDI output: {available_outputs[0]}")
            else:
                self.midiout = None
                print("No MIDI output ports available")
                
        except Exception as e:
            print(f"Error setting up MIDI ports: {e}")
            self.midiin = None
            self.midiout = None
    
    def _midi_callback(self, message, data=None):
        """
        Callback function for incoming MIDI messages.
        
        Args:
            message: MIDI message as a tuple (message, timestamp)
            data: Additional data (not used)
        """
        if not message:
            return
            
        midi_message, timestamp = message
        
        if not midi_message:
            return
            
        # Handle MIDI transport messages
        if len(midi_message) > 0:
            status = midi_message[0]
            
            if status == 0xFA:  # MIDI Start
                if self.debug:
                    print("MIDI Start received")
                self.tick_counter = 0
                self.current_bar = 0
                self.last_tick_time = time.time()
                self.midi_clock_present = True
                self.running = True
                self.transport_playing = True
                
            elif status == 0xFC:  # MIDI Stop
                if self.debug:
                    print("MIDI Stop received")
                self.transport_playing = False
                self.running = False
                self._stop_all_notes()  # Stop any currently playing notes
                
            elif status == 0xFB:  # MIDI Continue
                if self.debug:
                    print("MIDI Continue received")
                self.running = True
                self.transport_playing = True
                
            elif status == 0xF8:  # MIDI Clock
                self._process_clock_tick()
                
            elif status == 0xF2 and len(midi_message) >= 3:  # Song Position Pointer
                # Song position is in MIDI beats (16th notes), convert to our ticks
                # Each MIDI beat is 6 MIDI clock ticks (24 ticks per quarter note / 4)
                position_in_ticks = (midi_message[1] | (midi_message[2] << 7)) * 6
                self.tick_counter = position_in_ticks
                self.current_bar = position_in_ticks // self.ticks_per_bar
                if self.debug:
                    print(f"MIDI Song Position: {midi_message[1] | (midi_message[2] << 7)} (tick {position_in_ticks}, bar {self.current_bar})")
                
            elif status == 0xFF:  # MIDI Reset
                if self.debug:
                    print("MIDI Reset received")
                self.tick_counter = 0
                self.current_bar = 0
                self.midi_clock_present = False
                self.running = False
                self.transport_playing = False
                self.clear_loop()
                self._stop_all_notes()
                
            # Handle note messages for potential recording functionality
            elif (status & 0xF0) in (0x80, 0x90) and len(midi_message) >= 3:
                # Extract channel from status byte
                channel = status & 0x0F
                
                # Create a MidiNote object
                if (status & 0xF0) == 0x90:  # Note On
                    midi_note = MidiNote(0x90, midi_message[1], midi_message[2], channel, self.tick_counter / self.ppq)
                else:  # Note Off
                    midi_note = MidiNote(0x80, midi_message[1], midi_message[2], channel, self.tick_counter / self.ppq)
                
                # Just pass through to output if we're not recording
                if self.midiout:
                    self.midiout.send_message(midi_note.to_midi_message())
    
    def _process_clock_tick(self):
        """Process a single MIDI clock tick."""
        current_time = time.time()
        
        # Update tempo detection
        if self.last_tick_time is not None:
            interval = current_time - self.last_tick_time
            self.clock_intervals.append(interval)
            # Keep only the last 50 intervals for averaging
            if len(self.clock_intervals) > 50:
                self.clock_intervals.pop(0)
            if self.clock_intervals:
                avg_interval = sum(self.clock_intervals) / len(self.clock_intervals)
                # Calculate BPM: 24 clock ticks per quarter note
                new_tempo = 60.0 / (avg_interval * 24)
                
                # Only update if the tempo has changed significantly
                if abs(new_tempo - self.current_tempo) > 0.5:
                    self.current_tempo = new_tempo
                    if self.debug and not self.tempo_displayed:
                        print(f"MIDI Clock detected: Tempo set to {self.current_tempo:.1f} BPM")
                        self.tempo_displayed = True
        
        self.last_tick_time = current_time
        
        # Only process clock ticks if we're running
        if not self.running:
            return
            
        self.tick_counter += 1
        
        # Check if we've reached a new bar
        if self.tick_counter % self.ticks_per_bar == 0:
            self.current_bar += 1
            if self.debug:
                print(f"Bar {self.current_bar} (Tempo: {self.current_tempo:.1f} BPM)")
            self.tempo_displayed = False
        
        # Process any notes that need to be played at this tick
        self._process_notes_at_current_tick()
    
    def _process_notes_at_current_tick(self):
        """Process any notes that need to be played at the current tick."""
        # Only process notes if transport is playing
        if not self.transport_playing:
            return
            
        # Check for any pending note-offs that need to be sent
        current_time = time.time()
        remaining_note_offs = []
        
        for note_off_time, note_off_msg in self.pending_note_offs:
            if current_time >= note_off_time:
                if self.midiout:
                    self.midiout.send_message(note_off_msg)
                # Update active notes tracking
                if len(note_off_msg) >= 3:
                    note_num = note_off_msg[1]
                    channel = note_off_msg[0] & 0x0F
                    self.active_notes.pop((note_num, channel), None)
            else:
                remaining_note_offs.append((note_off_time, note_off_msg))
        
        self.pending_note_offs = remaining_note_offs
        
        # Check for notes to play at this tick
        current_beat = self.tick_counter / self.ppq
        
        # Process any notes in the loop
        for note in self.loop_notes:
            # Calculate the note's position in the current loop
            note_beat_in_loop = note.time % (self.time_signature[0] * (self.time_signature[1] / 4))
            current_beat_in_loop = current_beat % (self.time_signature[0] * (self.time_signature[1] / 4))
            
            # Check if this note should be played at this tick
            # We use a small epsilon to account for floating point errors
            epsilon = 0.01
            if (abs(note_beat_in_loop - current_beat_in_loop) < epsilon and 
                (note.message_type, note.note, current_beat) not in self.played_note_events):
                
                # Mark this note as played at this time
                self.played_note_events.add((note.message_type, note.note, current_beat))
                
                # Send the note message
                if self.midiout:
                    self.midiout.send_message(note.to_midi_message())
                
                # For note-on messages, schedule a note-off message
                if note.message_type == 0x90 and note.velocity > 0:
                    # Default note duration is one quarter note
                    note_duration_beats = 1.0
                    # Calculate when to send the note-off message
                    seconds_per_beat = 60.0 / self.current_tempo
                    note_off_time = current_time + (note_duration_beats * seconds_per_beat)
                    
                    # Create note-off message
                    note_off_msg = [0x80 | note.channel, note.note, 0]
                    
                    # Add to pending note-offs
                    self.pending_note_offs.append((note_off_time, note_off_msg))
                    
                    # Update active notes tracking
                    self.active_notes[(note.note, note.channel)] = note_off_time
        
        # Clean up played_note_events to prevent it from growing too large
        # Remove events that are more than one bar old
        current_bar_beat = current_beat - (current_beat % self.time_signature[0])
        self.played_note_events = {event for event in self.played_note_events 
                                 if event[2] >= current_bar_beat - self.time_signature[0]}
    
    def _stop_all_notes(self):
        """Stop all currently playing notes."""
        if self.midiout:
            # Send note-off messages for all active notes
            for (note, channel), _ in self.active_notes.items():
                note_off_msg = [0x80 | channel, note, 0]
                self.midiout.send_message(note_off_msg)
        
        # Clear active notes and pending note-offs
        self.active_notes = {}
        self.pending_note_offs = []
    
    def _handle_midi_message(self, message):
        """
        Handle incoming MIDI messages.
        
        Args:
            message: MIDI message to handle
        """
        # Convert message to rtmidi format and pass to callback
        if hasattr(message, 'bytes'):
            self._midi_callback((message.bytes(), 0))
        else:
            # Handle raw bytes
            self._midi_callback((message, 0))
    
    def add_note_to_loop(self, note):
        """
        Add a note to the loop.
        
        Args:
            note: MIDI note message to add to the loop (MidiNote object or list)
        """
        if isinstance(note, MidiNote):
            # Add the note to the loop
            self.loop_notes.append(note)
            
            # If this is a note_on with velocity > 0, check if we need to create a note_off
            if note.message_type == 0x90 and note.velocity > 0:
                # Look for a corresponding note_off
                for i, other_note in enumerate(self.loop_notes):
                    if ((other_note.message_type == 0x80) or 
                        (other_note.message_type == 0x90 and other_note.velocity == 0)) and \
                       other_note.note == note.note and \
                       other_note.channel == note.channel and \
                       other_note.time > note.time:
                        # Found a matching note_off, no need to create a new one
                        break
                else:
                    # No matching note_off found, create one with default duration
                    # This happens rarely as note_offs are usually created in _process_single_note
                    if self.debug:
                        print(f"Warning: Creating default note_off for note {note.note} as none was found")
                    
                    # Create a note_off message with a short default duration (0.25 beats)
                    note_off = MidiNote(0x80, note.note, 0, note.channel, note.time + 0.25)
                    self.loop_notes.append(note_off)
                
        elif isinstance(note, list) and len(note) >= 3:
            # Convert the list to a MidiNote object
            message_type = note[0] & 0xF0  # Extract message type (0x80, 0x90, etc.)
            channel = note[0] & 0x0F       # Extract channel (0-15)
            note_num = note[1]             # Note number
            velocity = note[2]             # Velocity
            
            # Create a MidiNote object with default time of 0
            midi_note = MidiNote(message_type, note_num, velocity, channel, 0)
            
            # Add to loop
            self.add_note_to_loop(midi_note)
        else:
            print(f"Warning: Invalid note data: {note}")
    
    def clear_loop(self):
        """Clear all notes from the loop."""
        # Turn off any active notes
        if self.midiout:
            for note_key, note in self.active_notes.items():
                note_off = MidiNote(0x80, note_key[0], 0, note_key[1], 0)
                self.midiout.send_message(note_off.to_midi_message())
        
        # Clear the tracking collections
        self.played_note_events.clear()
        self.active_notes.clear()
        self.pending_note_offs.clear()
        self.loop_notes.clear()
    
    def _process_single_note(self, note_data, channel, interval, position_in_beats=0, default_note_length=0.8):
        """
        Process a single note and add it to the loop.
        
        Args:
            note_data: Note data (number or dictionary)
            channel: MIDI channel to use
            interval: Time interval for note duration
            position_in_beats: Position of the note in beats (for timing)
            default_note_length: Default length of notes as a fraction of the interval between notes (0.0-1.0)
        """
        # If note_data is just a number, convert it to a dictionary
        if isinstance(note_data, (int, float)):
            note_data = {'note': int(note_data), 'velocity': 64}
        
        # Ensure note_data is a dictionary
        if isinstance(note_data, dict):
            note_num = note_data.get('note', 60)
            note_channel = note_data.get('channel', channel)
            
            # Check if this note is already playing and needs to be turned off
            for existing_note in self.loop_notes:
                if (existing_note.message_type == 0x90 and 
                    existing_note.note == note_num and 
                    existing_note.channel == note_channel and
                    existing_note.time < position_in_beats):
                    
                    # Find any existing note_off for this note
                    for note_off in self.loop_notes:
                        if (note_off.message_type == 0x80 and 
                            note_off.note == note_num and 
                            note_off.channel == note_channel and
                            note_off.time > existing_note.time):
                            
                            # Adjust the note_off time to be just before current position
                            if note_off.time > position_in_beats:
                                note_off.time = max(0, position_in_beats - 0.01)
                            break
            
            # Create note_on message
            note_on = MidiNote(0x90, note_num, note_data.get('velocity', 64), note_channel, position_in_beats)
            
            # Add note_on to the loop
            self.add_note_to_loop(note_on)
            
            # Determine note duration - use specified duration or default to a portion of the interval
            # Limit the default duration to the interval to prevent overlap with next note
            if 'duration' in note_data:
                # If duration is explicitly specified, use it as is
                duration = note_data['duration']
            else:
                # Otherwise calculate based on interval and default_note_length
                duration = min(interval * default_note_length, interval * 0.95)
            
            # Create note_off message
            note_off = MidiNote(0x80, note_num, 0, note_channel, position_in_beats + duration)
            
            # Add note_off to the loop
            self.add_note_to_loop(note_off)
        else:
            print(f"Warning: Invalid note data: {note_data}")
    
    def receive_notes_sequence(self, notes, num_bars=1, channel=0, quantize=True, output_device=None, default_note_length=0.8):
        """
        Receive a sequence of notes from the agent and distribute them across the specified number of bars.
        
        Args:
            notes: List of note dictionaries, MIDI note numbers, or lists of notes (for chords)
            num_bars: Number of bars to distribute the notes across
            channel: MIDI channel to use for the notes
            quantize: Whether to quantize the notes to the MIDI clock
            output_device: Name of the MIDI output device to use (from UI). If None, uses the current output_port.
            default_note_length: Default length of notes as a fraction of the interval between notes (0.0-1.0)
        """
        if not notes:
            print("Warning: Received empty notes sequence")
            return
        
        # If output_device is specified, try to set it
        if output_device:
            self.set_output_device(output_device)
            
        # Check if we have a valid output port
        if not self.midiout:
            print("Warning: No MIDI output port available. Notes will be processed but not played.")
        
        # Calculate the total number of beats in the specified bars
        beats_per_bar = self.time_signature[0]
        total_beats = beats_per_bar * num_bars
        
        # Count events (chords count as one event)
        num_events = len(notes)
        interval = total_beats / num_events if num_events > 0 else 1.0
        
        # Clear existing loop if any
        self.clear_loop()
        
        # Reset the played notes set
        self.played_note_events.clear()
        
        # If quantize is enabled and we have MIDI clock, wait for the next bar
        if quantize and self.midi_clock_present and self.running:
            # Calculate how many ticks until the next bar
            ticks_to_next_bar = self.ticks_per_bar - (self.tick_counter % self.ticks_per_bar)
            if ticks_to_next_bar < self.ticks_per_bar:
                print(f"Quantizing: waiting for next bar ({ticks_to_next_bar} ticks)")
                # We don't actually need to wait here, as the notes will be scheduled
                # relative to the current position in the MIDI clock
        
        # Process each note or chord
        for i, note_data in enumerate(notes):
            # Calculate the position of this event in beats
            position_in_beats = i * interval
            
            # For each new note/chord position, ensure any previous notes at earlier positions
            # have their note_off messages scheduled before the current position
            for note in self.loop_notes:
                if note.message_type == 0x80 and note.time > position_in_beats:
                    # Adjust note_off time to be just before the current position
                    note.time = max(0, position_in_beats - 0.01)
            
            # Handle different types of note data
            if isinstance(note_data, list):
                # This is a chord (list of notes to be played simultaneously)
                for chord_note in note_data:
                    # All chord notes start at the same position
                    self._process_single_note(chord_note, channel, interval, position_in_beats, default_note_length)
            elif isinstance(note_data, (int, float)):
                # This is a single note number
                self._process_single_note(note_data, channel, interval, position_in_beats, default_note_length)
            elif isinstance(note_data, dict):
                # This is a note dictionary
                self._process_single_note(note_data, channel, interval, position_in_beats, default_note_length)
            else:
                print(f"Warning: Invalid note data in sequence: {note_data}")
        
        print(f"Added {num_events} note events distributed across {num_bars} bars to the loop")
        
        # Don't automatically start playback - wait for MIDI start command instead
        # if not self.running and len(self.loop_notes) > 0:
        #     print("Starting playback automatically")
        #     self.running = True
        
        if len(self.loop_notes) > 0 and not self.running:
            print("Notes added to loop. Waiting for MIDI start command to begin playback.")
    
    def set_output_device(self, device_name):
        """
        Set the MIDI output device to use.
        
        Args:
            device_name: Name of the MIDI output device to use
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            available_outputs = rtmidi.MidiOut().get_ports()
            
            if device_name in available_outputs:
                # Close existing output port if any
                if self.midiout:
                    self.midiout.close_port()
                
                # Open new output port
                self.midiout = rtmidi.MidiOut()
                self.midiout.open_port(available_outputs.index(device_name))
                print(f"Connected to MIDI output: {device_name}")
                return True
            else:
                print(f"MIDI output device '{device_name}' not found. Available devices: {available_outputs}")
                return False
        except Exception as e:
            print(f"Error setting MIDI output device: {e}")
            return False
    
    def start(self):
        """Start the MIDI event loop."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("MIDI event loop started")
        self.tempo_displayed = False  # Reset tempo display flag when starting

    def stop(self):
        """Stop the MIDI event loop."""
        # Set running flag to False
        self.running = False
        
        # Turn off any active notes
        if self.midiout:
            for note_key, note in self.active_notes.items():
                note_off = MidiNote(0x80, note_key[0], 0, note_key[1], 0)
                self.midiout.send_message(note_off.to_midi_message())
        
        # Wait for thread to finish if it's running
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        
        # Close MIDI ports
        if self.midiin:
            self.midiin.close_port()
            del self.midiin
        if self.midiout:
            self.midiout.close_port()
            del self.midiout
        
        print("MIDI event loop stopped")

    def _run_loop(self):
        """Main loop function that runs in a separate thread."""
        self.last_tick_time = time.time()
        last_internal_tick = time.time()
        
        while self.running:
            current_time = time.time()
            
            # If we're not receiving MIDI clock, generate our own timing
            if not self.midi_clock_present:
                # Calculate sleep time based on tempo (quarter note duration)
                quarter_note_duration = 60.0 / self.default_tempo
                tick_duration = quarter_note_duration / self.ppq
                
                # Check if it's time for a new tick
                if current_time - last_internal_tick >= tick_duration:
                    self.tick_counter += 1
                    last_internal_tick = current_time
                    
                    # Every quarter note (24 ticks), play scheduled notes
                    if self.tick_counter % self.ppq == 0:
                        self._process_notes_at_current_tick()
                        
                    # Check if we've completed a bar
                    if self.tick_counter % self.ticks_per_bar == 0:
                        self.current_bar += 1
                        if self.debug:
                            print(f"Bar {self.current_bar} (internal clock)")
                
                # Sleep a small amount to avoid busy waiting
                time.sleep(min(tick_duration / 10, 0.001))
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

class MidiNote:
    """
    A class to represent a MIDI note with additional timing information.
    This is used to provide a compatible interface for rtmidi.
    """
    def __init__(self, message_type, note, velocity, channel=0, time=0):
        """
        Initialize a MIDI note.
        
        Args:
            message_type: MIDI message type (0x90 for note_on, 0x80 for note_off)
            note: MIDI note number
            velocity: MIDI velocity
            channel: MIDI channel
            time: Time in beats when this note should be played
        """
        self.message_type = message_type
        self.note = note
        self.velocity = velocity
        self.channel = channel
        self.time = time
        
    def to_midi_message(self):
        """Convert to a MIDI message that can be sent via rtmidi."""
        return [self.message_type | (self.channel & 0x0F), self.note, self.velocity]
        
    def __getitem__(self, index):
        """Allow indexing like a list for compatibility with existing code."""
        if index == 0:
            return self.message_type
        elif index == 1:
            return self.note
        elif index == 2:
            return self.velocity
        else:
            raise IndexError("MidiNote index out of range")
            
    def __len__(self):
        """Return the length of the MIDI message."""
        return 3
