# API Overview

The public entry point is `PropertyRadarClient`. Resource clients are exposed
as lazy properties and share the top-level client's HTTP transport.

Detailed resource pages are added with the endpoint implementation slices.
The packaged endpoint manifest maps all 37 documented operations to these nine
resource clients and records their mutation and charge classifications.
