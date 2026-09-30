import SwiftUI
import AVFoundation

final class SoundPlayer {
    private var player: AVAudioPlayer?

    init() {
        try? AVAudioSession.sharedInstance().setCategory(.playback)
        try? AVAudioSession.sharedInstance().setActive(true)
        if let url = Bundle.main.url(forResource: "faah", withExtension: "mp3") {
            player = try? AVAudioPlayer(contentsOf: url)
            player?.prepareToPlay()
        }
    }

    func play() {
        player?.currentTime = 0
        player?.play()
    }
}

struct ContentView: View {
    private let sound = SoundPlayer()
    @State private var pressed = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            Button {
                sound.play()
                UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                pressed = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { pressed = false }
            } label: {
                Text("FAAH")
                    .font(.system(size: 56, weight: .black, design: .rounded))
                    .foregroundColor(.white)
                    .frame(width: 280, height: 280)
                    .background(Circle().fill(Color.red))
                    .scaleEffect(pressed ? 0.9 : 1)
                    .animation(.spring(response: 0.2, dampingFraction: 0.5), value: pressed)
            }
            .buttonStyle(.plain)
        }
    }
}
