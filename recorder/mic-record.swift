// mic-record OUT.wav: record the default microphone to a 16 kHz mono 16-bit WAV until SIGINT or SIGTERM.
//
// Replaces ffmpeg's avfoundation input in dictate.sh: ffmpeg dropped about one 11 ms audio buffer in seven
// (122 holes, 1.3 s of a 9.55 s recording, closed up in the file) and started about 0.5 s late, so whisper heard
// clipped words. AVAudioRecorder records through Core Audio without dropping buffers. See docs/gotchas.md.
// Build: swiftc -O mic-record.swift -o mic-record
import AVFoundation
import Foundation

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write("usage: mic-record OUT.wav\n".data(using: .utf8)!)
    exit(2)
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let settings: [String: Any] = [
    AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000.0, AVNumberOfChannelsKey: 1,
    AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false,
]
let recorder: AVAudioRecorder
do {
    recorder = try AVAudioRecorder(url: url, settings: settings)
} catch {
    FileHandle.standardError.write("mic-record: \(error.localizedDescription)\n".data(using: .utf8)!)
    exit(1)
}
guard recorder.prepareToRecord(), recorder.record() else {
    FileHandle.standardError.write("mic-record: could not start recording (microphone permission?)\n".data(using: .utf8)!)
    exit(1)
}
// Stop cleanly on SIGINT or SIGTERM so the WAV header is written.
var sources: [DispatchSourceSignal] = []
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler { recorder.stop(); exit(0) }
    source.resume()
    sources.append(source)
}
RunLoop.main.run()
