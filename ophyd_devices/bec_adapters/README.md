# BEC device-library adapters

`OphydProvider` implements the neutral `bec_lib.device_backend` contracts for
existing ophyd devices. The BEC server calls per-device `OphydHandler` methods;
this package owns native metadata, kinds, staging, RPC normalization, callbacks,
logging and resource cleanup. BEC owns request context and Redis publication.

Message ingress snapshots receipt-time scan context; tree-local event fences keep
accepted publication ahead of request completion. Read ancestry prevents queued
feedback while preserving the first changed peer. Failure summaries stay bounded
per subscription/live fence. Failed-set stop runs on owned recovery workers;
commands on that tree are rejected until recovery drains, while reads, observation
and explicit stop remain available. Close drains recovery before destruction.

Existing device classes and configuration files need no changes. This requires
the matching BEC checkout containing `bec_lib.device_backend`; deploy both packages
together. Production ophyd-async is outside this extraction. The test-only asyncio
provider in BEC demonstrates loop ownership, independently admitted stop, pushed
events, dependency waits and cleanup without any ophyd/Bluesky base classes.

See the coordinated BEC checkout's `docs/device_backend.md` for interface ownership,
compatibility seams, execution/timeout policy, install order, release-floor updates
and validation commands. Actual first-release versions must be allocated before
publishing; the current package version/floors are not a promise that old BEC
releases contain this contract. Public user documentation belongs in bec_docs.
