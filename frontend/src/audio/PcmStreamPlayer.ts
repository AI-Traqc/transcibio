/**
 * Gapless playback of streamed int16 PCM frames via the Web Audio API.
 *
 * Each frame is wrapped in an AudioBuffer at the stream's native sample rate and
 * scheduled to begin exactly where the previous one ends (sample-accurate), so
 * contiguous frames play without clicks or gaps. `stop()` flushes the queue
 * instantly — the hook needed for barge-in in a later phase.
 *
 * The AudioContext runs at its own default rate; buffers carry their own sample
 * rate (Piper 22050 / Kokoro 24000) and Web Audio resamples them. This is more
 * robust than forcing a context sample rate, which some browsers reject.
 */
export class PcmStreamPlayer {
  private readonly ctx: AudioContext;
  private sampleRate: number;
  private nextStartTime = 0;
  private readonly active = new Set<AudioBufferSourceNode>();

  constructor(sampleRate: number) {
    this.sampleRate = sampleRate;
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    this.ctx = new Ctor();
    // Created inside a user gesture, but Chrome can still start it suspended.
    void this.ctx.resume();
  }

  /** Update the rate for subsequent buffers (from the stream's `start` header). */
  setSampleRate(sampleRate: number): void {
    if (sampleRate > 0) this.sampleRate = sampleRate;
  }

  /** Schedule one frame of raw int16 little-endian mono PCM for playback. */
  enqueue(pcm: ArrayBuffer): void {
    const samples = new Int16Array(pcm);
    if (samples.length === 0) return;
    if (this.ctx.state === "suspended") void this.ctx.resume();

    const buffer = this.ctx.createBuffer(1, samples.length, this.sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) {
      channel[i] = samples[i] / 32768;
    }

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);

    // Small lead on the first frame so we never schedule in the past.
    const startAt = Math.max(this.ctx.currentTime + 0.06, this.nextStartTime);
    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;

    this.active.add(source);
    source.onended = () => this.active.delete(source);
  }

  /** Stop all scheduled audio immediately and reset the schedule (barge-in). */
  stop(): void {
    for (const source of this.active) {
      try {
        source.stop();
      } catch {
        // already stopped
      }
    }
    this.active.clear();
    this.nextStartTime = 0;
  }

  async close(): Promise<void> {
    this.stop();
    await this.ctx.close();
  }
}
