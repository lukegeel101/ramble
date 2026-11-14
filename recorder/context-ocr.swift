// Recognize a single active-window PNG received on stdin. No image files or network access.
import Foundation
import Vision

let data = FileHandle.standardInput.readDataToEndOfFile()
guard !data.isEmpty, data.count <= 12_000_000 else { exit(2) }
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
// Preserve names and source-code vocabulary rather than autocorrecting them into ordinary words.
do {
    try VNImageRequestHandler(data: data).perform([request])
    let lines = (request.results ?? []).compactMap { item -> String? in
        guard let candidate = item.topCandidates(1).first, candidate.confidence >= 0.3 else { return nil }
        return candidate.string
    }
    print(String(lines.joined(separator: "\n").suffix(32000)), terminator: "")
} catch {
    fputs("context OCR failed\n", stderr)
    exit(1)
}
