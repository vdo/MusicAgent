import mido
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
        
        # Check environment variable if debug is None
        if debug is None:
            debug_env = os.environ.get('DEBUG', '').lower()
            self.debug = debug_env in ('true', '1', 'yes', 'y')
        else:
            self.debug = debug
            
        self.tempo_displayed = False
        
        # Initialize ports to None
        self.input_port = None
        self.output_port = None
        
        # Try to open MIDI ports if auto_open_ports is True
        if auto_open_ports:
            self._open_default_ports()
    
    def _open_default_ports(self):
        """Open the default MIDI input and output ports."""
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
    
    def set_output_device(self, device_name):
        """
        Set the MIDI output device to use.
        
        Args:
            device_name: Name of the MIDI output device to use
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            available_outputs = mido.get_output_names()
            
            if device_name in available_outputs:
                # Close existing output port if any
                if self.output_port:
                    self.output_port.close()
                
                # Open new output port
                self.output_port = mido.open_output(device_name)
                print(f"Connected to MIDI output: {device_name}")
                return True
            else:
                print(f"MIDI output device '{device_name}' not found. Available devices: {available_outputs}")
                return False
        except Exception as e:
            print(f"Error setting MIDI output device: {e}")
            return False
    
    def _handle_midi_message(self, message):
        """
        Handle incoming MIDI messages.
        
        Args:
            message: MIDI message to handle
        """
        # Handle MIDI system real-time messages (status bytes 0xF8-0xFF)
        if message.type == 'clock':  # 0xF8 (248) - Timing Clock
            self.midi_clock_present = True
            self._process_clock_tick()
        
        elif message.type == 'start':  # 0xFA (250) - Start
            print("MIDI Start received")
            self.tick_counter = 0
            self.current_bar = 0
            self.last_tick_time = time.time()
            self.midi_clock_present = True
            self.running = True
            
        elif message.type == 'stop':  # 0xFC (252) - Stop
            print("MIDI Stop received")
            self.running = False
            
        elif message.type == 'continue':  # 0xFB (251) - Continue
            print("MIDI Continue received")
            self.running = True
            
        elif message.type == 'song_position':  # 0xF2 (242) - Song Position Pointer
            # Song position is in MIDI beats (16th notes), convert to our ticks
            # Each MIDI beat is 6 MIDI clock ticks (24 ticks per quarter note / 4)
            position_in_ticks = message.pos * 6
            self.tick_counter = position_in_ticks
            self.current_bar = position_in_ticks // self.ticks_per_bar
            print(f"MIDI Song Position: {message.pos} (tick {position_in_ticks}, bar {self.current_bar})")
            
        elif message.type == 'reset':  # 0xFF (255) - Reset
            print("MIDI Reset received")
            self.tick_counter = 0
            self.current_bar = 0
            self.midi_clock_present = False
            self.running = False
            self.clear_loop()
            
        # Handle note messages for potential recording functionality
        elif message.type in ('note_on', 'note_off') and self.running:
            # Just pass through to output if we're not recording
            if self.output_port:
                self.output_port.send(message)
    
    def _process_clock_tick(self):
        """Process a single MIDI clock tick."""
        current_time = time.time()
        
        # Only process clock ticks if we're running
        if not self.running:
            return
            
        self.tick_counter += 1
        
        # Calculate tempo from MIDI clock if we have received enough ticks
        if self.last_tick_time is not None:
            tick_interval = current_time - self.last_tick_time
            
            # Only update tempo every quarter note (24 ticks) to smooth out jitter
            if self.tick_counter % self.ppq == 0:
                # Calculate time for a quarter note (24 MIDI clock ticks)
                quarter_note_time = tick_interval * self.ppq
                if quarter_note_time > 0:
                    # Convert to BPM (60 seconds / quarter_note_time)
                    new_tempo = 60.0 / quarter_note_time
                    
                    # Apply a simple low-pass filter to smooth tempo changes
                    # (80% previous tempo, 20% new tempo)
                    self.current_tempo = 0.8 * self.current_tempo + 0.2 * new_tempo
                    
                    # Only print tempo changes that are significant
                    if abs(self.current_tempo - self.default_tempo) > 1.0:
                        if self.debug:
                            print(f"Current tempo: {self.current_tempo:.1f} BPM")
                        elif not self.tempo_displayed:
                            print(f"Current tempo: {self.current_tempo:.1f} BPM")
                            self.tempo_displayed = True
        
        self.last_tick_time = current_time
        
        # Check if we've completed a bar
        if self.tick_counter % self.ticks_per_bar == 0:
            self.current_bar += 1
            if self.debug:
                print(f"Bar {self.current_bar}")
        
        # Every quarter note (24 ticks), check if we need to play notes
        if self.tick_counter % self.ppq == 0:
            self._play_scheduled_notes()
    
    def _play_scheduled_notes(self):
        """Play any notes that are scheduled to be played."""
        if not self.running or not self.output_port:
            return
    
        # Get the current beat position
        current_beat = (self.tick_counter / self.ppq) % (self.time_signature[0] * 4)  # 4 beats per bar
        total_beats_in_loop = self.time_signature[0] * 4  # Total beats in a loop (4 beats per bar)
        
        # First process any pending note_offs
        pending_note_offs_to_keep = []
        for note_off in self.pending_note_offs:
            # Check if it's time to send this note_off
            note_beat_position = note_off.time % total_beats_in_loop
            
            # If we're close to the note_off time, send it
            if abs(current_beat - note_beat_position) < 0.1 or (current_beat < 0.1 and note_beat_position > (total_beats_in_loop - 0.1)):
                # Send the note_off message
                self.output_port.send(note_off)
                
                # Remove this note from active notes
                note_key = (note_off.note, note_off.channel)
                if note_key in self.active_notes:
                    del self.active_notes[note_key]
                    
                if self.debug:
                    print(f"Note OFF: {note_off.note} on channel {note_off.channel+1} at beat {current_beat:.2f}")
            else:
                # Keep this note_off for future processing
                pending_note_offs_to_keep.append(note_off)
                
        # Update the pending note_offs list
        self.pending_note_offs = pending_note_offs_to_keep
        
        # Sort notes by their time attribute
        sorted_notes = sorted(self.loop_notes, key=lambda note: note.time if hasattr(note, 'time') else 0)
        
        # Play notes that should be played at this beat position
        for note in sorted_notes:
            # Skip notes that aren't note_on messages
            if note.type != 'note_on':
                continue
                
            # Create a unique identifier for each note event
            note_id = (note.type, note.note, note.time, note.channel)
            
            # Skip notes that have already been played in this loop
            if note_id in self.played_note_events:
                continue
                
            # Calculate if this note should be played at this beat
            note_beat_position = note.time % total_beats_in_loop
            
            # If we're close to the note's beat position, play it
            # Use a small tolerance to account for timing jitter
            if abs(current_beat - note_beat_position) < 0.1 or (current_beat < 0.1 and note_beat_position > (total_beats_in_loop - 0.1)):
                # Check if this note is already playing (to prevent overlapping identical notes)
                note_key = (note.note, note.channel)
                
                # If velocity is 0, this is effectively a note_off
                if note.velocity == 0:
                    if note_key in self.active_notes:
                        # Turn off the note
                        self.output_port.send(note)
                        del self.active_notes[note_key]
                        if self.debug:
                            print(f"Note OFF (velocity=0): {note.note} on channel {note.channel+1} at beat {current_beat:.2f}")
                else:
                    # For regular note_on messages
                    # Check if we need to turn off an existing note first
                    if note_key in self.active_notes:
                        # Create a note_off message to stop the currently playing note
                        note_off = mido.Message('note_off', note=note.note, velocity=0, channel=note.channel, time=current_beat)
                        self.output_port.send(note_off)
                        if self.debug:
                            print(f"Pre-emptive Note OFF: {note.note} on channel {note.channel+1} at beat {current_beat:.2f}")
                    
                    # Send the note_on message
                    self.output_port.send(note)
                    
                    # Mark this note as active
                    self.active_notes[note_key] = note
                    
                    if self.debug:
                        print(f"Note ON: {note.note} on channel {note.channel+1} at beat {current_beat:.2f}")
                
                # Mark the note as played in this loop
                self.played_note_events.add(note_id)
    
    def add_note_to_loop(self, note):
        """
        Add a note to the loop.
        
        Args:
            note: MIDI note message to add to the loop
        """
        if isinstance(note, mido.Message):
            # Make sure the note has a time attribute
            if not hasattr(note, 'time'):
                note.time = 0
                
            # Handle note_on and note_off messages
            if note.type == 'note_on' and hasattr(note, 'note'):
                # Add the note_on message to the loop
                self.loop_notes.append(note)
                
                # If this is a note_off (velocity=0), we don't need to create a separate note_off
                if note.velocity > 0:
                    # Look for a corresponding note_off
                    for i, other_note in enumerate(self.loop_notes):
                        if (other_note.type == 'note_off' or 
                            (other_note.type == 'note_on' and other_note.velocity == 0)) and \
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
                        note_off = mido.Message('note_off', 
                                               note=note.note, 
                                               velocity=0, 
                                               channel=note.channel, 
                                               time=note.time + 0.25)
                        self.loop_notes.append(note_off)
                
            elif note.type == 'note_off' and hasattr(note, 'note'):
                # Add the note_off message to the loop
                self.loop_notes.append(note)
            else:
                print(f"Warning: Ignoring MIDI message without proper note properties: {note}")
        else:
            print(f"Warning: Tried to add invalid MIDI message to loop: {note}")
    
    def clear_loop(self):
        """Clear all notes from the loop."""
        # Turn off any active notes
        if self.output_port:
            for note_key, note in self.active_notes.items():
                note_off = mido.Message('note_off', note=note_key[0], velocity=0, channel=note_key[1])
                self.output_port.send(note_off)
        
        # Clear the tracking collections
        self.played_note_events.clear()
        self.active_notes.clear()
        self.pending_note_offs.clear()
        
        # Clear the loop
        self.loop_notes = []
    
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
            # Create note_on message
            note_on = mido.Message('note_on',
                                  note=note_data.get('note', 60),
                                  velocity=note_data.get('velocity', 64),
                                  channel=note_data.get('channel', channel),
                                  time=position_in_beats)
            
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
            note_off = mido.Message('note_off',
                                   note=note_data.get('note', 60),
                                   velocity=0,
                                   channel=note_data.get('channel', channel),
                                   time=position_in_beats + duration)
            
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
        if not self.output_port:
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
            
            # Handle different types of note data
            if isinstance(note_data, list):
                # This is a chord (list of notes to be played simultaneously)
                for chord_note in note_data:
                    # All chord notes start at the same position and can overlap
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
                        self._play_scheduled_notes()
                        
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
