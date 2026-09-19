# Held-out evaluation

The evaluation harness scores 10-20 existing assignment runs without copying assignment text, answers, student identity, or course evidence into the shared repository. Start from `.calvin-autonomy/templates/evaluation-manifest.json` after setup, replace each generic `run_ref` with a private workspace run reference, and record only the expected outcomes and blocker fragments. The harness maps `run_ref` to the runtime internally; the shared schema does not expose runtime identity metadata.

Run the harness with:

    .calvin-autonomy/bin/coursework --workspace workspace evaluate evaluation-manifest.json --out evaluation-report.json

Each case requires expected values for readiness, structured-verification pass/fail, stale detection, and blocker fragments. A blocker fragment is matched case-insensitively within the runtime's full blocker message, which keeps the manifest stable when a message adds useful detail. Blocked cases must name at least one expected blocker. `minimum_requirement_coverage` is optional; use `1.0` for cases that must cover every requirement.

The report includes readiness accuracy, false-ready count and rate, false-blocked count, expected-blocker recall, structural requirement coverage, verification outcome accuracy, and stale-detection accuracy. A false-ready result means the runtime marked a case ready even though its expected outcome was blocked; treat any such result as a release blocker.

Correction time is calculated only for cases that include both timezone-aware timestamps:

    "timestamps": {
      "failure_detected_at": "2026-01-01T14:00:00Z",
      "corrected_at": "2026-01-01T14:30:00Z"
    }

The harness reports the elapsed seconds for that case plus the mean, median, and maximum across timestamped cases. Omit `timestamps` when the correction interval was not observed. It rejects incomplete, timezone-free, or reversed intervals rather than estimating them.

Keep the manifest and report in the private workspace when run IDs or evaluation history should remain private. The installed template is synthetic and is not evidence that the named runs exist or passed.
