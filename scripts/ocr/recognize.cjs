const path = require('node:path');
const {createWorker} = require('tesseract.js');
const {langPath} = require('@tesseract.js-data/eng');
const readline = require('node:readline');

(async () => {
  const worker = await createWorker('eng', 1, {
    langPath, gzip: true,
    corePath: path.dirname(require.resolve('tesseract.js-core/package.json')),
    cachePath: process.env.FILEORA_OCR_CACHE,
    logger: () => {},
  });
  try {
    async function recognize(filename) {
      const {data} = await worker.recognize(filename, {}, {tsv: true});
      const words = (data.tsv || '').split('\n').slice(1).map(line => line.split('\t')).filter(fields => fields[0] === '5' && fields[11]?.trim()).map(fields => ({text: fields[11], x: Number(fields[6]), y: Number(fields[7]), width: Number(fields[8]), height: Number(fields[9])}));
      return {text: data.text, words};
    }
    if (process.argv[2] === '--stream') {
      const input = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
      for await (const line of input) {
        try { process.stdout.write(JSON.stringify(await recognize(JSON.parse(line).path)) + '\n'); }
        catch { process.stdout.write(JSON.stringify({error: 'OCR_FAILED'}) + '\n'); }
      }
    } else {
      process.stdout.write(JSON.stringify(await recognize(process.argv[2])));
    }
  } finally {await worker.terminate();}
})().catch(() => {process.stderr.write('Local OCR failed'); process.exitCode = 1;});
