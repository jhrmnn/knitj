Alternative front-end to IPython, in development.

### Architecture


Neptune watches an R-Markdown-like source file (with Python cells) for change. On change, it checks which cells changed, evaluates them, and sends the updated output to an HTML document via websocket.
