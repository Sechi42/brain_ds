#!/usr/bin/env python3
from __future__ import annotations

import sys

from brain_ds.ui.viewer import (  # re-exported for legacy imports/tests
    derive_output_path,
    load_graph,
    main,
    render_graph_data,
    render_graph_file,
    slugify,
)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
