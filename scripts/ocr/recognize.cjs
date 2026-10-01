const path = require('node:path');
const {createWorker} = require('tesseract.js');
const {langPath} = require('@tesseract.js-data/eng');

(async () => {
  const worker = await createWorker('eng', 1, {
    langPath, gzip: true,
    corePath: path.dirname(require.resolve('tesseract.js-core/package.json')),
    cachePath: process.env.FILEORA_OCR_CACHE,
    logger: () => {},
  });
  try {
    const {data} = await worker.recognize(process.argv[2], {}, {tsv: true});
    const words = (data.tsv || '').split('\n').slice(1).map(line => line.split('\t')).filter(fields => fields[0] === '5' && fields[11]?.trim()).map(fields => ({text: fields[11], x: Number(fields[6]), y: Number(fields[7]), width: Number(fields[8]), height: Number(fields[9])}));
    process.stdout.write(JSON.stringify({text: data.text, words}));
  } finally {await worker.terminate();}
})().catch(() => {process.stderr.write('Local OCR failed'); process.exitCode = 1;});
