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



model = HfApiModel(
model_id='Qwen/Qwen2.5-Coder-32B-Instruct',
provider=None,
)

web_search = WebSearch()
visit_webpage = VisitWebpage()
final_answer = FinalAnswer()
notes_from_chord = NotesFromChord()
all_modes = AllModes()

with open(os.path.join(CURRENT_DIR, "prompts.yaml"), 'r') as stream:
    prompt_templates = yaml.safe_load(stream)

agent = CodeAgent(
    model=model,
    tools=[web_search, visit_webpage, notes_from_chord, all_modes, final_answer],
    managed_agents=[],
    max_steps=10,
    verbosity_level=2,
    grammar=None,
    planning_interval=None,
    name=None,
    description="A music assitant agent.",
    prompt_templates=prompt_templates
)
if __name__ == "__main__":
    GradioUI(agent).launch()
