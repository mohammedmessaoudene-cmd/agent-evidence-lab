# P05 sources and third-party rights

The included LICENSE covers the project's original adapter, independently implemented control, protocol, tests, review text and original synthetic values and provenance notes. Internal AI-assisted reviews are not independent human attestations. A license for original code does not transfer ownership of a third-party framework or authorize the use of customer data.

## OpenHTF

OpenHTF is separately licensed under Apache-2.0. Version 1.6.3 at commit `87426bad5bc3d846b3025a2dc18987e020cedb00` generated the four small historical native JSON exports. Their scalar values were assigned in software; they do not represent hardware measurements. No OpenHTF implementation is copied into this subdirectory, and the importer does not require OpenHTF at runtime.

- Source: https://github.com/google/openhtf/tree/87426bad5bc3d846b3025a2dc18987e020cedb00
- Upstream license: https://github.com/google/openhtf/blob/87426bad5bc3d846b3025a2dc18987e020cedb00/LICENSE
- Native record definitions: https://github.com/google/openhtf/blob/87426bad5bc3d846b3025a2dc18987e020cedb00/openhtf/core/test_record.py

The native JSON attachment field retains OpenHTF's inline encoding of an original synthetic provenance note. It is part of the documented fixture format, not an opaque distribution archive. The note is not a third-party corpus. All delivered source files and review text are otherwise plain UTF-8 text. The corrective review did not regenerate the exports with an SDK.

## Runtime and exclusions

Python's standard library is the only runtime dependency of this subdirectory. Python and any separately installed framework retain their own licenses. No radio dataset or derivative under CC BY-NC-SA, customer evidence, private research archive, account credential or private Page identifier is part of this public candidate. Code licensing, dataset permissions, framework licensing and any future service agreement are separate questions.
