# SPDX-License-Identifier: MIT

"""ctrlx-baseline framework: the parts every ctrlX app shares.

These files are copied unchanged from ctrlx-baseline/framework into each app. Don't edit them in an app:
change them in ctrlx-baseline (reviewed, versioned) and copy them again. tools/check.py reports a copy
that differs from every baseline version as a "local change".

  bus.py       Data Layer client (ctrlxdatalayer library), plain Python values
  rest.py      the same interface over the ctrlX REST API, with the calling user's token
  fakebus.py   simulated Data Layer with the same interface, for development and tests
  provider.py  the app's own Data Layer nodes
  web.py       HTTP server behind the ctrlX reverse proxy: routing, errors, bodies, static files
  appdata.py   JSON files in the app data of the active configuration (atomic writes, outside changes)
  runtime.py   start-up: snap or development, active configuration, Data Layer, web server, main loop
"""
