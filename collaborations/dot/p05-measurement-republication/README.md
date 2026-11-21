# Recognizing repeated measurement publications

In one normal PowerDuck testbed recording, three devices published **3,300 repeats and 292 new versions** of measurement data. Treating every arrival as a new version misclassified all 3,300 repeats. Watching one numeric channel missed 40 of the 292 version changes. In one of those 40 cases, the device advanced its state counter and changed its event time while the entire measurement payload stayed byte-for-byte identical. [Aggregate results](observed.json)

The researchers connected a public-grid voltage measurement to three physical devices and recorded their GOOSE publications at a switch mirror port. This analysis uses the first normal session, `01-normal-1`, in PowerDuck 1.0.1. Its 6,259 recorded frames include 3,595 measurement publications. The first frame in each measurement stream establishes its starting state, leaving 3,592 consecutive pairs for comparison. [Dataset](https://doi.org/10.5281/zenodo.6974112) · [Testbed and recording procedure](https://doi.org/10.1145/3546096.3546102)

## How to reproduce the counts

Group the measurement publications by device and measurement stream, preserving capture order. For each consecutive pair, classify a **repeat** when the state counter and event time stay the same, the sequence counter advances by one, and all measurement bytes match. Classify a **new version** when the state counter advances by one, the sequence resets to zero and the event time changes. The lab checked capture times, counters and the first numeric channel against the authors' IPAL transcription. Both files describe the same recording.

For each pair, compare that classification with two rules. The first predicts a new version when the capture time advances. The second predicts a new version when the first numeric channel, indexed `000` in IPAL, changes value. The rules were specified after the initial repeat count and before tallying their disagreements.

| Rule | New versions recognized out of 292 | Repeats called new out of 3,300 |
|---|---:|---:|
| Capture time advances | 292 | 3,300 |
| First channel changes | 252 | 0 |

## What the clocks establish

The GOOSE event time describes the published state change. All 3,595 measurement publications carry the time-quality byte `0x3f`, with the clock-unsynchronized flag set and accuracy unspecified. The interval between arrivals can be measured on the recorder's clock. The physical acquisition time for each channel and the delay to a caller's decision remain unknown. The recording also leaves application-level fresh reads, cache reads, physical faults and false alarms unmeasured by this comparison. [Time-quality flags](https://support.mz-automation.de/doc/libiec61850/net/latest/class_i_e_c61850_1_1_common_1_1_mms_value.html) · [Accuracy encoding](https://download.copadata.com/fileadmin/user_upload/Downloads/Dokumentation/810SP0/FRENCH/Driver/IEC850.pdf)

Sven Zemanek, Immanuel Hacker, Konrad Wolsing, Eric Wagner, Martin Henze and Martin Serror published PowerDuck under CC BY 4.0. The Dot laboratory derived the counts and rule comparison from the normal recording. [Source and version](https://zenodo.org/records/6974112) · [Dataset license](https://creativecommons.org/licenses/by/4.0/)
