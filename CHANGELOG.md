# Changelog

All notable changes to this package will be documented here.

## 1.0.0 - 2026-09-25

- Publish under MIT with metadata for gramix-io/gramix-python-sdk.
- Validate decimal amounts, ISO timestamps, pagination bounds, and response status.
- Accept UUID versions 6–8 in addition to versions 1–5.
- Test every endpoint through a local HTTP server, including all Premium durations.
- Document request/response formats, pagination, and error handling.
- Add Windows and macOS compatibility jobs to CI.

- Disable automatic HTTP redirects to prevent forwarding credentials.
- Wrap incomplete HTTP responses in TransportError and close error responses.
- Validate optional order quantities against their declared integer types.
- Share UUID and enum validation rules and use one source for package version.
- Add HTTP transport regression tests and Ruff checks to CI.

- Align GRAM purchases with the API: integer amounts and GRAM payment only.
- Reject non-integer Premium durations before sending requests.
- Document GitHub installation and test distributable artifacts in CI.

- Implement all seven Gramix API v1 endpoints.
- Add request validation, timeouts, custom transports, and typed exceptions.
- Ship inline typing, validate documented response schemas, and parse order
  webhook payloads.
