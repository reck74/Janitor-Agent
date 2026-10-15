This Linux x86_64 source/bootstrap candidate contains Janitor Desktop, SHA-256 checksums, source/engine metadata, and native smoke evidence tied to the source commit. It is a prerelease for acceptance; the stable updater will not select it.

Download the matching AppImage, `.sha256` and `.json` sidecars. Verify the checksum with `sha256sum --check <filename>.sha256`, mark the AppImage executable, then launch it. Janitor requires Docker, MiniMax and local or cloud Honcho. Existing installations should retain their profile/configuration backup and the previous AppImage during acceptance.

Acceptance still requires a complete first launch with actual credentials, memory derivation/retrieval, profile/session preservation and a real N→N+1 update. The native smoke confirms identity, bootstrap provenance, onboarding/cancellation and packaged PTY; it does not certify those service integrations. Stable publication is a separate decision after the acceptance report is complete.
