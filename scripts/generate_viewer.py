#!/usr/bin/env python3
from __future__ import annotations

import sys

from brain_ds.ui.viewer import (  # re-exported for legacy imports/tests
    main,
)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
