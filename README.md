---
title: MusicAgent
emoji: 🎹
colorFrom: purple
colorTo: red
sdk: gradio
sdk_version: 5.16.1
app_file: app.py
pinned: false
tags:
- smolagents
- agent
- music
- mingus
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

# MusicAgent: Your AI Music Theory and MIDI Assistant

## Overview

MusicAgent is an AI-powered assistant designed to help musicians, producers, and music enthusiasts with music theory concepts and MIDI control. It combines the power of large language models with specialized music tools to provide a comprehensive music assistance experience.

## Features

### Music Theory Assistance
- **Chord Analysis**: Identify and explain chord structures, inversions, and functions
- **Scale and Mode Information**: Get detailed information about scales and modes in music
- **Music Theory Concepts**: Learn about harmony, rhythm, melody, and other music theory concepts

### MIDI Control and Interaction
- **MIDI Device Selection**: Choose from available MIDI input and output devices directly from the UI
- **MIDI Channel Selection**: Select which MIDI channel to use for sending messages
- **MIDI Sequence Tool**: Send note sequences, chord progressions, and complex rhythmic patterns to your MIDI devices
## Integration with Patchbox OS and PiSound
- **TBD**

## How It Works

MusicAgent is built on a modular architecture that combines several key components:

1. **AI Language Model**: Powered by Qwen2.5-Coder-32B-Instruct, the agent can understand natural language queries about music and provide detailed explanations.

2. **MIDI Event Loop**: The core component that handles MIDI message processing, timing, and communication with MIDI devices. It allows for:
   - Real-time MIDI input/output
   - Scheduling of MIDI events with precise timing
   - Handling of complex musical patterns

3. **Gradio Web Interface**: A user-friendly interface that allows you to:
   - Chat with the AI assistant
   - Configure MIDI settings
   - Select input/output devices and channels

## Getting Started

1. **Launch the Application**: Run `python app.py` to start the web interface
2. **Configure MIDI Settings**: 
   - Open the "MIDI Settings" accordion in the UI
   - Select your preferred MIDI input and output devices
   - Choose the MIDI channel you want to use
3. **Ask Music-Related Questions**: Type your music theory questions or MIDI control requests in the chat interface

## Technical Details

- **MIDI Implementation**: Uses the `mido` and `python-rtmidi` libraries for MIDI communication
- **Agent Framework**: Built on the `smolagents` framework for AI agent capabilities
- **Web Interface**: Utilizes Gradio for an interactive web-based UI


## TODO

* Improve system prompt
* LLM selection and integration (OpenAI, Anthropic, etc.)
* Integration in patchbox OS for Raspberry Pi.
