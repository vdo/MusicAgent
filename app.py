import yaml
import os
import mido
import gradio as gr
from smolagents import CodeAgent, HfApiModel

# Get current directory path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

from tools.web_search import DuckDuckGoSearchTool as WebSearch
from tools.visit_webpage import VisitWebpageTool as VisitWebpage
from tools.chords import NotesFromChordTool as NotesFromChord
from tools.chords import AllModesTool as AllModes
from tools.final_answer import FinalAnswerTool as FinalAnswer
from tools.midi_tools import MidiSequenceTool
from midi_loop import MidiEventLoop

# Get available MIDI devices
available_inputs = mido.get_input_names()
available_outputs = mido.get_output_names()

# Add "None" option to the lists
available_inputs_with_none = ["None"] + available_inputs
available_outputs_with_none = ["None"] + available_outputs

# Default MIDI channels (0-15)
midi_channels = list(range(16))

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

# Initialize the MIDI tool with default channel 0
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
)

# Function to handle MIDI input port selection
def select_midi_input(port_name):
    if hasattr(midi_loop, 'input_port') and midi_loop.input_port is not None:
        midi_loop.input_port.close()
    
    if port_name == "None":
        midi_loop.input_port = None
        return f"MIDI input disconnected"
    
    try:
        midi_loop.input_port = mido.open_input(port_name, callback=midi_loop._handle_midi_message)
        return f"Connected to MIDI input: {port_name}"
    except Exception as e:
        return f"Error connecting to MIDI input {port_name}: {e}"

# Function to handle MIDI output port selection
def select_midi_output(port_name):
    if hasattr(midi_loop, 'output_port') and midi_loop.output_port is not None:
        midi_loop.output_port.close()
    
    if port_name == "None":
        midi_loop.output_port = None
        return f"MIDI output disconnected"
    
    try:
        midi_loop.output_port = mido.open_output(port_name)
        return f"Connected to MIDI output: {port_name}"
    except Exception as e:
        return f"Error connecting to MIDI output {port_name}: {e}"

# Function to handle MIDI channel selection
def select_midi_channel(channel):
    midi_sequence.default_channel = channel
    return f"MIDI channel set to: {channel}"

# Function to refresh available MIDI devices
def refresh_midi_devices():
    global available_inputs, available_outputs
    available_inputs = mido.get_input_names()
    available_outputs = mido.get_output_names()
    
    # Add "None" option to the lists
    available_inputs_with_none = ["None"] + available_inputs
    available_outputs_with_none = ["None"] + available_outputs
    
    return (
        gr.Dropdown.update(choices=available_inputs_with_none),
        gr.Dropdown.update(choices=available_outputs_with_none),
        f"Found {len(available_inputs)} input(s) and {len(available_outputs)} output(s)"
    )

# Start the MIDI event loop
midi_loop.start()

# Create the Gradio Blocks interface
with gr.Blocks(title="MusicAgent") as ui:
    gr.Markdown("# MusicAgent")
    gr.Markdown("A MIDI control smolagent with some musical hallucinations.")
    
    with gr.Accordion("MIDI Settings", open=False):
        with gr.Row():
            with gr.Column():
                midi_input_dropdown = gr.Dropdown(
                    choices=available_inputs_with_none,
                    value="None" if not available_inputs else available_inputs_with_none[0],
                    label="MIDI Input Device"
                )
                midi_input_status = gr.Textbox(label="Input Status", interactive=False)
                
            with gr.Column():
                midi_output_dropdown = gr.Dropdown(
                    choices=available_outputs_with_none,
                    value="None" if not available_outputs else available_outputs_with_none[0],
                    label="MIDI Output Device"
                )
                midi_output_status = gr.Textbox(label="Output Status", interactive=False)
                
            with gr.Column():
                midi_channel_dropdown = gr.Dropdown(
                    choices=midi_channels,
                    value=0,
                    label="MIDI Channel"
                )
                midi_channel_status = gr.Textbox(label="Channel Status", interactive=False)
                refresh_button = gr.Button("Refresh MIDI Devices")
    
    # Connect event handlers
    midi_input_dropdown.change(
        select_midi_input,
        inputs=[midi_input_dropdown],
        outputs=[midi_input_status]
    )
    
    midi_output_dropdown.change(
        select_midi_output,
        inputs=[midi_output_dropdown],
        outputs=[midi_output_status]
    )
    
    midi_channel_dropdown.change(
        select_midi_channel,
        inputs=[midi_channel_dropdown],
        outputs=[midi_channel_status]
    )
    
    refresh_button.click(
        refresh_midi_devices,
        inputs=[],
        outputs=[midi_input_dropdown, midi_output_dropdown, midi_channel_status]
    )
    
    # Initialize the selected devices
    if midi_input_dropdown.value != "None":
        select_midi_input(midi_input_dropdown.value)
    if midi_output_dropdown.value != "None":
        select_midi_output(midi_output_dropdown.value)
    
    # Create the chat interface
    chatbot = gr.Chatbot(height=500, type="messages")
    msg = gr.Textbox(
        placeholder="Ask me about music theory, chords, or MIDI control...",
        container=False
    )
    clear = gr.ClearButton([msg, chatbot])
    
    def respond(message, chat_history):
        # Add user message to chat history
        chat_history.append({"role": "user", "content": message})
        
        # Get response from agent
        response = agent.run(message)
        
        # Add agent response to chat history
        chat_history.append({"role": "assistant", "content": response})
        
        return "", chat_history
    
    msg.submit(respond, [msg, chatbot], [msg, chatbot])

try:
    ui.launch(share=True)
finally:
    # Make sure to stop the MIDI event loop when the app is closed
    midi_loop.stop()
