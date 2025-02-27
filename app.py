import yaml
import os
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
midi_loop = MidiEventLoop(default_tempo=120, time_signature=(4, 4))

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
