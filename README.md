Alternative front-end to Jupyter kernels.

### Motivation

-   Jupyter notebooks mix input and output, complicating source code management
-   R Markdown does not properly support Python
-   Development of Jupyter notebooks and R Markdown (RStudio) mandates a third-party editor

### Architecture

```
source.md --[file change]--> Neptune <--[HTTP/websocket]--> HTML DOM
```

Neptune watches an R Markdown source file for change. On file change, it evaluates the changed code cells in a Jupyter kernel, and sends the updated output to an HTML document. The HTML document can request reevaluation of any code cell.