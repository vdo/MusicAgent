import yaml
import os
import mido
from smolagents import GradioUI, CodeAgent, HfApiModel

# Get current directory path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

from tools.web_search import DuckDuckGoSearchTool as WebSearch
from tools.visit_webpage import VisitWebpageTool as VisitWebpage
from tools.chords import NotesFromChordTool as NotesFromChord
from tools.chords import AllModesTool as AllModes
from tools.final_answer import FinalAnswerTool as FinalAnswer
from tools.midi_tools import MidiSequenceTool
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


# Get available MIDI devices
available_inputs = mido.get_input_names()
available_outputs = mido.get_output_names()

# Let the user select MIDI input and output devices
print("\n=== MIDI Device Selection ===")
selected_input = select_midi_device(available_inputs, "input")
selected_output = select_midi_device(available_outputs, "output")

model = HfApiModel(
model_id='Qwen/Qwen2.5-Coder-32B-Instruct',
provider=None,
)

web_search = WebSearch()
visit_webpage = VisitWebpage()
final_answer = FinalAnswer()
notes_from_chord = NotesFromChord()
all_modes = AllModes()

# Initialize the MIDI event loop with default tempo and time signature
midi_loop = MidiEventLoop(default_tempo=120, time_signature=(4, 4), auto_open_ports=False)

# Manually set the input and output ports based on user selection
if hasattr(midi_loop, 'input_port') and midi_loop.input_port is not None:
    midi_loop.input_port.close()
if hasattr(midi_loop, 'output_port') and midi_loop.output_port is not None:
    midi_loop.output_port.close()

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

# Initialize the MIDI tool
midi_sequence = MidiSequenceTool(midi_loop=midi_loop)

with open(os.path.join(CURRENT_DIR, "prompts.yaml"), 'r') as stream:
    prompt_templates = yaml.safe_load(stream)

agent = CodeAgent(
    model=model,
    tools=[
        web_search, 
        visit_webpage, 
        notes_from_chord, 
        all_modes, 
        final_answer, 
        midi_sequence
    ],
    managed_agents=[],
    max_steps=10,
    verbosity_level=2,
    grammar=None,
    planning_interval=None,
    additional_authorized_imports=["mingus", "mido"],
    name=None,
    description="A music assitant agent.",
    prompt_templates=prompt_templates
)

if __name__ == "__main__":
    # Start the MIDI event loop
    midi_loop.start()
    
    try:
        # Launch the Gradio UI
        GradioUI(agent).launch()
    finally:
        # Make sure to stop the MIDI event loop when the app exits
        midi_loop.stop()
