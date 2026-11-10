# SPDX-License-Identifier: MIT

"""3D Model Builder: Build 3D viewer models from STL files and bind them to ctrlX MOTION axes"""

# The app's identity (ctrlx-baseline STANDARD.md, "Identity"); everything else is derived from it.
NAME = "model-builder"          # snap name = URL /model-builder = Data Layer root model-builder/ = app data folder model-builder/
TITLE = "3D Model Builder"       # sidebar entry
ENV = "MODEL_BUILDER"           # prefix of the development settings: MODEL_BUILDER_FAKE, MODEL_BUILDER_PORT, MODEL_BUILDER_DATA, ...
PORT = 12521           # TCP port in development (in the snap: the proxy's unix socket)
