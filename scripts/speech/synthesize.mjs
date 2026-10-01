// A local fixture generator; this synthesizer is not part of the application.
import fs from 'node:fs';
import initialize from '@echogarden/espeak-ng-emscripten';

const [textPath, outputPath] = process.argv.slice(2);
if (!textPath || !outputPath) throw new Error('Usage: node synthesize.mjs text.txt output.wav');
const module = await initialize();
const voice = new module.eSpeakNGWorker();
voice.set_voice('en-us');
voice.set_rate(0.85);
const chunks = [];
voice.synthesize(fs.readFileSync(textPath, 'utf8'), samples => {
  if (samples?.length) chunks.push(Buffer.from(new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength)));
});
const pcm = Buffer.concat(chunks);
if (!pcm.length) throw new Error('Speech synthesis produced no samples');
const header = Buffer.alloc(44);
header.write('RIFF', 0); header.writeUInt32LE(36 + pcm.length, 4); header.write('WAVEfmt ', 8);
header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
header.writeUInt32LE(22050, 24); header.writeUInt32LE(44100, 28);
header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
header.write('data', 36); header.writeUInt32LE(pcm.length, 40);
fs.writeFileSync(outputPath, Buffer.concat([header, pcm]));
