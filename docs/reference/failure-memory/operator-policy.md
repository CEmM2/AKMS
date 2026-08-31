# Operator policy

1. Preserve the append-only canonical registry, including failed lessons and
   stable IDs.
2. Do not hand-edit generated lesson nodes, routes, graph, mirrors, loadouts,
   manifests, or provider results.
3. Treat the global AKMS vault as read-only. Promotion is a separate human
   decision and is not implemented by failure memory.
4. Keep `repo2md_command` as an argv array. Preflight must verify executable
   source identity, required flags, version, commit/dirty policy, fixture pack,
   AKMS schema, and public-source digest.
5. Run explicit refresh before dispatch when current state is required.
   `require-current` verifies freshness under the lock; it does not refresh in a
   read path.
6. A provider fingerprint is valid only for the baseline, role, route index,
   graph, project configuration, and diff that produced it.
7. External publication, tags, PyPI upload, and GitHub releases remain operator
   actions. A checked-in release pin records a verified candidate; it does not
   prove those external actions occurred.
