# udsflashreport

`udsflashreport` is planned as an open-source, deterministic UDS/ISO-TP flash trace fault attribution engine.

The v1 target is offline analysis of ASC/BLF traces with evidence-chain reports and a PySide6 desktop viewer. It does not perform live diagnostic communication or ECU flashing.

## Project status

M0 skeleton development is in progress. The frozen implementation specification is maintained separately during development and will be reflected under `spec/`.

## Safety and responsibility

This project is provided for engineering analysis and testing. Results must be independently validated before use in any vehicle, ECU, production, or safety-relevant workflow. Users are responsible for their own use, validation, and consequences. No accuracy, fitness, or safety guarantee is provided.

The project has no affiliation with Vector, any OEM, or any other referenced vendor.

## License

This project is licensed under the MIT License; see `LICENSE`. Third-party dependencies retain their own licenses; see `THIRD_PARTY_NOTICES.md`.
