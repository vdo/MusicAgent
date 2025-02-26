from typing import Any, Optional
from smolagents.tools import Tool
from mingus.core import chords as Chords
from mingus.core import scales as Scales


class AllModesTool(Tool):
    name = "all_modes"
    description = """
    This tool returns a comma-separated list of all available scale modes in our tools. Useful to get chords within a mode."""
    inputs = {}
    output_type = "string"

    def forward(self):
        return ', '.join([s.__name__ for s in Scales._Scale.__subclasses__()])

    def __init__(self, *args, **kwargs):
        self.is_initialized = False


class NotesFromChordTool(Tool):
    name = "notes_from_chord"
    description = """
    This tool returns a comma-separated list of notes from a chord in shorthand notation."""
    inputs = {'chord': {'type': 'string', 'description': "The chord to convert to notes in shorthand notation. Examples: 'Cmaj7', 'Dm9', 'EM'."}}
    output_type = "string"

    def forward(self, chord: str):
        try:
            return ', '.join(Chords.from_shorthand(chord))
        except:
            return "Invalid or unknown chord!"

    def __init__(self, *args, **kwargs):
        self.is_initialized = False
